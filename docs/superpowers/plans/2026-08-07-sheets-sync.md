# Sheets Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold Google Sheets synchronization (data + column B formula/dropdown + row-level conditional formatting) into `run_pipeline.py` as its final step, replacing the manual CSV import.

**Architecture:** A new `sheets_sync.py` reads the highest offer ID already present in the target sheet, appends only newer rows from `output/import_YYYYMMDD.csv`, reproduces column B's formula and the row-level conditional formatting on those new rows, and gates on a persistent error-state file after a failed run. `auth.py` is generalized to serve a second, separately-scoped OAuth token for the Sheets API alongside the existing Gmail one.

**Tech Stack:** Python 3.13, `google-api-python-client` (Sheets API v4, already a dependency), `pytest`, `ruff`.

## Global Constraints

- CSV separator `;`, UTF-8 encoding (existing project convention).
- Code, comments, commit messages: English. Plain hyphens only, never em dashes, anywhere (code, comments, docs, commit messages, no exceptions).
- No new external service calls in unit tests — Sheets API interactions are mocked via `unittest.mock`.
- `token_sheets.json` is never committed — must be `.gitignore`d (verify it's covered by the existing `token.json`/`credentials.json` patterns; add an explicit entry if the existing glob doesn't already match it).
- `spreadsheet_id` is externalized in config, never hardcoded — starts pointed at the user's duplicated test sheet, switches to the real sheet only once validated.
- Real push is the default (no `--dry-run` needed to write for real) — matches every other script in this pipeline.
- No automatic retry on a transient Sheets API error.

---

### Task 1: Feasibility spike — inspect the duplicated sheet's formatting

**This task requires you (the user) to run the script against your duplicated test sheet and report back what it prints — the findings feed directly into Tasks 6 and 7, written after this task completes.**

**Files:**
- Create: `inspect_sheet_formatting.py`

**Interfaces:**
- Consumes: `auth.get_credentials` (Task 2 — write Task 2 first, since this script needs the generalized signature).
- Produces: no importable interface — this is a one-shot diagnostic script, its output (not its code) is what later tasks consume.

- [ ] **Step 1: Write `inspect_sheet_formatting.py`**

```python
#!/usr/bin/env python3
"""One-shot inspection tool: prints column B's formula (from a sample data
row), the sheet's data validation rules (the dropdown), and its row-level
conditional formatting rules, read directly from a Google Sheet via the
Sheets API.

Run this against a DUPLICATED test sheet, never the real one — its only
purpose is to discover exactly what sheets_sync.py needs to replicate, so it
can be transcribed correctly instead of guessed.

Usage:
    python3 inspect_sheet_formatting.py <spreadsheet_id> <sheet_name>
"""

import argparse
import json

from googleapiclient.discovery import build

import auth
from sheets_sync import SHEETS_SCOPES, TOKEN_SHEETS_FILE


def get_sheets_service():
    creds = auth.get_credentials(scopes=SHEETS_SCOPES, token_file=TOKEN_SHEETS_FILE)
    return build("sheets", "v4", credentials=creds)


def inspect(spreadsheet_id: str, sheet_name: str) -> dict:
    """Return the sheet metadata needed to replicate formatting: a sample of
    row 2's cell formulas/validation/format (representative of any data row),
    plus the sheet-wide conditional format rules."""
    service = get_sheets_service()
    return service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        ranges=[f"{sheet_name}!A1:Z3"],
        fields=(
            "sheets(properties,conditionalFormats,"
            "data.rowData.values(userEnteredValue,dataValidation,userEnteredFormat))"
        ),
        includeGridData=True,
    ).execute()


def main(spreadsheet_id: str, sheet_name: str) -> None:
    result = inspect(spreadsheet_id, sheet_name)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spreadsheet_id")
    parser.add_argument("sheet_name")
    args = parser.parse_args()
    main(args.spreadsheet_id, args.sheet_name)
```

This depends on `sheets_sync.SHEETS_SCOPES`/`TOKEN_SHEETS_FILE` (Task 4) and `auth.get_credentials`'s generalized signature (Task 2) — write this script last, after Tasks 2 and 4, even though it's listed first here as the conceptual first step of the feature.

- [ ] **Step 2 (manual): Run it against the duplicated sheet**

Run: `python3 inspect_sheet_formatting.py <duplicated-spreadsheet-id> <sheet-name>`

This opens a browser for the first-time Sheets OAuth consent (same pattern as `auth.py`'s existing Gmail flow, new scope). Report the full JSON output back — specifically: column B's formula string (row 2's `userEnteredValue.formulaValue`), the dropdown's `dataValidation` rule (the 3 values and, separately, the `userEnteredFormat` colors for each), and every entry under `conditionalFormats` (the row-level duplicate/blacklist highlighting rules).

**Do not proceed to Tasks 6/7 until this output has been reviewed together and the exact formula/rules are confirmed.**

- [ ] **Step 3: Commit**

```bash
git add inspect_sheet_formatting.py
git commit -m "$(cat <<'EOF'
feat: add sheet formatting inspection spike script

Modified files:
- inspect_sheet_formatting.py - one-shot tool to read column B's formula, data validation, and conditional format rules from a Google Sheet via the API
EOF
)"
```

---

### Task 2: Generalize `auth.py` for multiple scopes/tokens

**Files:**
- Modify: `auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Produces: `get_credentials(scopes: list[str] | None = None, token_file: Path | None = None) -> Credentials`. Defaults preserve the existing Gmail behavior exactly (`fetch_gmail.py`'s zero-argument call site needs no changes). Consumed by Task 4 (`sheets_sync.py`) and Task 1 (`inspect_sheet_formatting.py`).

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_auth.py, alongside the 3 existing tests
from pathlib import Path


def test_get_credentials_accepts_custom_scopes_and_token_file(tmp_path):
    custom_token = tmp_path / "custom_token.json"
    custom_token.write_text("{}", encoding="utf-8")
    custom_scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    fake_creds = MagicMock(valid=True)
    with patch.object(auth.Credentials, "from_authorized_user_file", return_value=fake_creds) as mock_load:
        result = auth.get_credentials(scopes=custom_scopes, token_file=custom_token)

    mock_load.assert_called_once_with(str(custom_token), custom_scopes)
    assert result is fake_creds


def test_get_credentials_defaults_use_module_constants(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token.json")
    (tmp_path / "token.json").write_text("{}", encoding="utf-8")

    fake_creds = MagicMock(valid=True)
    with patch.object(auth.Credentials, "from_authorized_user_file", return_value=fake_creds) as mock_load:
        auth.get_credentials()

    mock_load.assert_called_once_with(str(tmp_path / "token.json"), auth.SCOPES)
```

The 3 existing tests (`test_get_credentials_returns_valid_cached_token`, `test_get_credentials_refreshes_expired_token`, `test_get_credentials_runs_flow_when_no_token_file`) must keep passing unchanged — they call `auth.get_credentials()` with no arguments and monkeypatch `auth.TOKEN_FILE`/`auth.CREDENTIALS_FILE` directly, exactly the behavior the defaults below must preserve.

- [ ] **Step 2: Run tests to verify the 2 new ones fail**

Run: `pytest tests/test_auth.py -v`
Expected: the 2 new tests FAIL (`TypeError: get_credentials() got an unexpected keyword argument 'scopes'` or similar), the 3 existing ones still PASS.

- [ ] **Step 3: Modify `auth.py`**

Replace the `get_credentials` function:

```python
def get_credentials(scopes: list[str] | None = None, token_file: Path | None = None) -> Credentials:
    """Return valid credentials for the given scopes, refreshing or running the
    interactive OAuth2 flow as needed. Writes/updates the given token file.

    Defaults to the Gmail read-only scope and TOKEN_FILE, preserving existing
    zero-argument call sites. Resolved inside the function body (not as
    parameter defaults) so callers can still monkeypatch the module-level
    SCOPES/TOKEN_FILE constants and have get_credentials() pick up the change."""
    if scopes is None:
        scopes = SCOPES
    if token_file is None:
        token_file = TOKEN_FILE

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), scopes)
        creds = flow.run_local_server(port=0)

    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds
```

Nothing else in `auth.py` changes — `SCOPES`, `CREDENTIALS_FILE`, `TOKEN_FILE` module constants stay as they are.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add auth.py tests/test_auth.py
git commit -m "$(cat <<'EOF'
feat: generalize auth.get_credentials for multiple scopes and tokens

Modified files:
- auth.py - get_credentials() accepts optional scopes/token_file, defaulting to the existing Gmail values so fetch_gmail.py needs no changes
- tests/test_auth.py - tests for the custom-scopes path and the default-resolution path
EOF
)"
```

---

### Task 3: Config additions for the Sheets sync target

**Files:**
- Modify: `config/config.json`

**Interfaces:**
- Produces: `config["sheets_sync"]["spreadsheet_id"]`, `config["sheets_sync"]["sheet_name"]`. Consumed by Task 4 (`sheets_sync.py`).

- [ ] **Step 1: Add a `sheets_sync` section to `config/config.json`**

Add a new top-level key (keep the rest of the file untouched):

```json
  "sheets_sync": {
    "spreadsheet_id": "",
    "sheet_name": "Offres"
  },
```

- [ ] **Step 2 (manual): Fill in the real values**

Set `spreadsheet_id` to your **duplicated test sheet's** ID (the long ID in its URL, between `/d/` and `/edit`) — never the real sheet's ID at this stage. Confirm `sheet_name` matches your actual tab name (adjust the `"Offres"` placeholder above if your tab is named differently).

- [ ] **Step 3: Commit**

```bash
git add config/config.json
git commit -m "$(cat <<'EOF'
feat: add sheets_sync config section

Modified files:
- config/config.json - spreadsheet_id (test sheet) and sheet_name for the new Sheets sync step
EOF
)"
```

---

### Task 4: `sheets_sync.py` — ID comparison and dedup core

**Files:**
- Create: `sheets_sync.py`
- Test: `tests/test_sheets_sync.py`

**Interfaces:**
- Produces: `SHEETS_SCOPES`, `TOKEN_SHEETS_FILE`, `offer_id_number(offer_id: str) -> int`, `read_import_rows(import_csv_path: Path) -> list[dict]`, `rows_to_sync(import_rows: list[dict], last_synced_id: int) -> int`, `read_last_synced_id(service, spreadsheet_id: str, sheet_name: str) -> int`. Consumed by Task 1 (`SHEETS_SCOPES`/`TOKEN_SHEETS_FILE`), Task 5, Task 6/7 (to be detailed after the spike), Task 8 (`run_pipeline.py`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sheets_sync.py
import csv
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sheets_sync import offer_id_number, read_import_rows, read_last_synced_id, rows_to_sync


def test_offer_id_number_extracts_the_numeric_suffix():
    assert offer_id_number("E006545") == 6545


def test_offer_id_number_rejects_unexpected_format():
    with pytest.raises(ValueError):
        offer_id_number("not-an-id")


def test_read_import_rows_reads_semicolon_csv(tmp_path):
    csv_path = tmp_path / "import_20260101.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ID", "Titre"], delimiter=";")
        writer.writeheader()
        writer.writerow({"ID": "E000001", "Titre": "Dev"})

    rows = read_import_rows(csv_path)

    assert rows == [{"ID": "E000001", "Titre": "Dev"}]


def test_rows_to_sync_filters_by_id_strictly_greater(monkeypatch):
    rows = [{"ID": "E000001"}, {"ID": "E000002"}, {"ID": "E000003"}]

    result = rows_to_sync(rows, last_synced_id=1)

    assert result == [{"ID": "E000002"}, {"ID": "E000003"}]


def test_rows_to_sync_preserves_csv_order():
    rows = [{"ID": "E000005"}, {"ID": "E000002"}, {"ID": "E000003"}]

    result = rows_to_sync(rows, last_synced_id=1)

    assert result == [{"ID": "E000005"}, {"ID": "E000002"}, {"ID": "E000003"}]


def test_read_last_synced_id_returns_max_id_number():
    service = MagicMock()
    values_resource = service.spreadsheets.return_value.values.return_value
    values_resource.get.return_value.execute.return_value = {
        "values": [["E000001"], ["E000003"], ["E000002"]]
    }

    result = read_last_synced_id(service, "sheet-id", "Offres")

    assert result == 3


def test_read_last_synced_id_returns_zero_when_sheet_has_no_data_rows():
    service = MagicMock()
    values_resource = service.spreadsheets.return_value.values.return_value
    values_resource.get.return_value.execute.return_value = {}

    result = read_last_synced_id(service, "sheet-id", "Offres")

    assert result == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sheets_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sheets_sync'`

- [ ] **Step 3: Write `sheets_sync.py` (this task's portion only)**

```python
#!/usr/bin/env python3
"""Syncs new offers from the latest output/import_YYYYMMDD.csv into a Google
Sheet: appends rows the sheet doesn't already have (compared by offer ID),
reproduces column B's formula/dropdown, and extends row-level conditional
formatting to the new rows. Gated behind a persistent error state after a
failed run (see check_error_gate/write_error_state/clear_error_state).

Usage:
    python3 sheets_sync.py [--dry-run]
    python3 sheets_sync.py --ack-error
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "config" / "config.json"
LOGS_DIR = ROOT / "logs"
OUTPUT_DIR = ROOT / "output"

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TOKEN_SHEETS_FILE = ROOT / "token_sheets.json"


def load_config() -> dict:
    with CONFIG_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def offer_id_number(offer_id: str) -> int:
    """'E006545' -> 6545. Raises ValueError on an unexpected format."""
    if not offer_id.startswith("E") or not offer_id[1:].isdigit():
        raise ValueError(f"Unexpected offer ID format: {offer_id!r}")
    return int(offer_id[1:])


def read_import_rows(import_csv_path: Path) -> list[dict]:
    """Read an output/import_YYYYMMDD.csv file's rows as dicts."""
    with import_csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def rows_to_sync(import_rows: list[dict], last_synced_id: int) -> list[dict]:
    """Rows whose ID is strictly greater than last_synced_id, in CSV order."""
    return [row for row in import_rows if offer_id_number(row["ID"]) > last_synced_id]


def read_last_synced_id(service, spreadsheet_id: str, sheet_name: str) -> int:
    """Highest offer ID number currently in column A of the sheet, or 0 if
    the sheet has no data rows yet."""
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A2:A"
    ).execute()
    values = result.get("values", [])
    ids = [offer_id_number(row[0]) for row in values if row]
    return max(ids) if ids else 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sheets_sync.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add sheets_sync.py tests/test_sheets_sync.py
git commit -m "$(cat <<'EOF'
feat: add sheets_sync.py ID comparison and dedup core

Modified files:
- sheets_sync.py - offer_id_number, read_import_rows, rows_to_sync, read_last_synced_id: the idempotency mechanism (compare against the sheet's own max ID, no separate state file)
- tests/test_sheets_sync.py - unit tests for all four functions, Sheets API mocked
EOF
)"
```

---

### Task 5: `sheets_sync.py` — persistent error-state gate

**Files:**
- Modify: `sheets_sync.py`
- Test: `tests/test_sheets_sync.py`

**Interfaces:**
- Produces: `ERROR_STATE_FILE`, `write_error_state(message: str) -> None`, `read_error_state() -> dict | None`, `clear_error_state() -> None`, `check_error_gate() -> None`. Consumed by Task 8 (`run_pipeline.py`) and Tasks 6/7 (the real sync path, to be detailed after the spike).

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_sheets_sync.py
import pytest

from sheets_sync import check_error_gate, clear_error_state, read_error_state, write_error_state


def test_write_then_read_error_state_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "sheets_sync_error.json")

    write_error_state("Sheets API quota exceeded")
    state = read_error_state()

    assert state["message"] == "Sheets API quota exceeded"
    assert "recorded_at" in state


def test_read_error_state_returns_none_when_no_error(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "sheets_sync_error.json")

    assert read_error_state() is None


def test_clear_error_state_removes_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "sheets_sync_error.json")
    write_error_state("some error")

    clear_error_state()

    assert read_error_state() is None


def test_clear_error_state_is_a_no_op_when_nothing_to_clear(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "sheets_sync_error.json")

    clear_error_state()  # must not raise


def test_check_error_gate_raises_when_error_state_exists(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "sheets_sync_error.json")
    write_error_state("Sheets API quota exceeded")

    with pytest.raises(SystemExit, match="Sheets API quota exceeded"):
        check_error_gate()


def test_check_error_gate_passes_silently_when_no_error(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "sheets_sync_error.json")

    check_error_gate()  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sheets_sync.py -v`
Expected: the 6 new tests FAIL (`ImportError`/`AttributeError`), the 6 from Task 4 still PASS.

- [ ] **Step 3: Add to `sheets_sync.py`**

Add near the top imports:

```python
from datetime import datetime, timezone
```

Add after the module constants:

```python
ERROR_STATE_FILE = LOGS_DIR / "sheets_sync_error.json"


def write_error_state(message: str) -> None:
    ERROR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ERROR_STATE_FILE.write_text(
        json.dumps({
            "message": message,
            "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }),
        encoding="utf-8",
    )


def read_error_state() -> dict | None:
    if not ERROR_STATE_FILE.exists():
        return None
    with ERROR_STATE_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def clear_error_state() -> None:
    ERROR_STATE_FILE.unlink(missing_ok=True)


def check_error_gate() -> None:
    """Raise SystemExit with the recorded error if an unacknowledged sync
    failure exists. Called at the start of sheets_sync's own run() and of
    run_pipeline.run_pipeline()."""
    state = read_error_state()
    if state is not None:
        raise SystemExit(
            f"Synchronisation Sheets bloquee : erreur non acquittee du {state['recorded_at']}\n"
            f"  {state['message']}\n"
            f"Acquitte avec : python3 sheets_sync.py --ack-error"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sheets_sync.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add sheets_sync.py tests/test_sheets_sync.py
git commit -m "$(cat <<'EOF'
feat: add sheets_sync.py persistent error-state gate

Modified files:
- sheets_sync.py - write_error_state/read_error_state/clear_error_state/check_error_gate: a failed sync blocks run_pipeline.py and sheets_sync.py until explicitly acknowledged, per design
- tests/test_sheets_sync.py - tests for the round-trip, the gate, and the no-op clear case
EOF
)"
```

---

### Task 6 and Task 7: to be written after Task 1's live findings

**Do not write these tasks yet.** Task 6 (writing new rows' values and column B's formula into the sheet) and Task 7 (extending row-level conditional formatting to the new rows) both need the exact formula text, dropdown values/colors, and conditional format rule definitions that only Task 1's live run against the duplicated sheet reveals. Writing them now would mean guessing at real values instead of transcribing them — exactly what Task 1 exists to avoid.

Once Task 1's output has been reviewed together, amend this plan document to insert the fully-specified Task 6 and Task 7 here, following the same TDD structure as every other task, then continue with Task 8 below (which only depends on their interface, not their internals).

---

### Task 8: `run_pipeline.py` — integrate the Sheets sync step

**Files:**
- Modify: `run_pipeline.py`
- Test: `tests/test_run_pipeline.py`

**Interfaces:**
- Consumes: `sheets_sync.check_error_gate() -> None` (Task 5), `sheets_sync.run(dry_run: bool) -> None` (Task 6/7 — not yet implemented when this task is written, but its signature is fixed here: a single required `dry_run: bool` parameter, no return value, matching the pattern of every other step function this orchestrator calls).

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_run_pipeline.py
def test_run_pipeline_calls_sheets_sync_last(monkeypatch):
    calls = []
    monkeypatch.setattr(run_pipeline.fetch_gmail, "run",
                        lambda dry_run, since_days=None: calls.append(("fetch", dry_run)))
    monkeypatch.setattr(run_pipeline.rename_eml, "run",
                        lambda dry_run, purge: calls.append(("rename", dry_run, purge)))
    monkeypatch.setattr(run_pipeline.extract_eml, "main",
                        lambda dry_run: calls.append(("extract", dry_run)))
    monkeypatch.setattr(run_pipeline.sheets_sync, "check_error_gate", lambda: None)
    monkeypatch.setattr(run_pipeline.sheets_sync, "run",
                        lambda dry_run: calls.append(("sheets_sync", dry_run)))

    run_pipeline.run_pipeline(dry_run=True)

    assert calls == [
        ("fetch", True),
        ("rename", True, False),
        ("extract", True),
        ("sheets_sync", True),
    ]


def test_run_pipeline_checks_error_gate_before_anything_else(monkeypatch):
    calls = []

    def failing_gate():
        calls.append("gate_checked")
        raise SystemExit("blocked")

    monkeypatch.setattr(run_pipeline.sheets_sync, "check_error_gate", failing_gate)
    monkeypatch.setattr(run_pipeline.fetch_gmail, "run",
                        lambda dry_run, since_days=None: calls.append("fetch"))

    with pytest.raises(SystemExit, match="blocked"):
        run_pipeline.run_pipeline(dry_run=True)

    assert calls == ["gate_checked"]
```

Note: the existing `test_run_pipeline_calls_steps_in_order` and `test_run_pipeline_stops_on_fetch_failure` tests must be updated too — they currently assert `calls == [("fetch", True), ("rename", True, False), ("extract", True)]` / `calls == []`; both need `run_pipeline.sheets_sync.check_error_gate` monkeypatched to a no-op (`lambda: None`) so they don't fail on the new gate check, and the first one's expected call list needs the same `("sheets_sync", True)` tuple appended (mirroring the new test above rather than duplicated here — update it directly).

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `pytest tests/test_run_pipeline.py -v`
Expected: FAIL — `run_pipeline` has no attribute `sheets_sync` yet.

- [ ] **Step 3: Modify `run_pipeline.py`**

Add to the imports:

```python
import sheets_sync
```

Replace `run_pipeline`:

```python
def run_pipeline(dry_run: bool, since_days: int | None = None) -> None:
    sheets_sync.check_error_gate()

    print("=== 1/4 - Fetch Gmail ===")
    fetch_gmail.run(dry_run=dry_run, since_days=since_days)

    print("\n=== 2/4 - Rename & index ===")
    rename_eml.run(dry_run=dry_run, purge=False)

    print("\n=== 3/4 - Extract offers ===")
    extract_eml.main(dry_run=dry_run)

    print("\n=== 4/4 - Sync to Google Sheets ===")
    sheets_sync.run(dry_run=dry_run)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_run_pipeline.py -v`
Expected: 4 passed

**This task cannot fully pass end to end until `sheets_sync.run()` exists (Task 6/7) — the tests above mock it out, so they pass regardless, but do not attempt a real (non-mocked) `run_pipeline.py` invocation until Task 6/7 land.**

- [ ] **Step 5: Commit**

```bash
git add run_pipeline.py tests/test_run_pipeline.py
git commit -m "$(cat <<'EOF'
feat: integrate sheets_sync as run_pipeline.py's final step

Modified files:
- run_pipeline.py - added sheets_sync.check_error_gate() at start and sheets_sync.run(dry_run) as step 4/4
- tests/test_run_pipeline.py - updated existing tests for the new step and gate check, added 2 new tests
EOF
)"
```

---

### Task 9: Documentation

**Files:**
- Modify: `README.md`
- Modify: `README.fr.md`

**Interfaces:**
- None (docs only).

- [ ] **Step 1: Update `README.md`**

- Update the pipeline diagram to show `sheets_sync.py` as the 4th step, ending at the real Sheet instead of `import_YYYYMMDD.csv` (keep `import_YYYYMMDD.csv` documented too — it's still produced, just no longer the end of the line).
- Add a `sheets_sync.py` section: what it does (compares the sheet's own max offer ID against the CSV, appends only newer rows, reproduces column B's formula/dropdown and row-level conditional formatting on those rows), usage (`--dry-run`, `--ack-error`), and the error-gate behavior (blocks `run_pipeline.py`/`sheets_sync.py` until acknowledged; `fetch_gmail.py`/`rename_eml.py`/`extract_eml.py` remain usable individually).
- Document the new `config.json` `sheets_sync` section (`spreadsheet_id`, `sheet_name`).
- Document the new `token_sheets.json` (separate OAuth token, `spreadsheets` scope, same `credentials.json` client as Gmail).
- Update the "Migration" section's post-merge checklist if relevant (this feature doesn't need a data migration, but note that switching `spreadsheet_id` from the test sheet to the real one is a required manual step before real use).

- [ ] **Step 2: Update `README.fr.md`**

Same structure and content, in French.

- [ ] **Step 3: Commit**

```bash
git add README.md README.fr.md
git commit -m "$(cat <<'EOF'
docs: document sheets_sync.py and the updated pipeline

Modified files:
- README.md - sheets_sync.py section, updated pipeline diagram, config/token documentation
- README.fr.md - same in French
EOF
)"
```

## Execution Notes

- Tasks 2, 3, 4, 5, 8, 9 are fully automatable now.
- Task 1 requires the user's direct participation (running the spike script against the duplicated sheet, reviewing its output) — do not attempt to script around this.
- Tasks 6 and 7 do not exist yet in this document. They must be written (following this same plan's TDD structure) after Task 1's findings are reviewed, before Task 8 can be exercised for real (its tests mock `sheets_sync.run()`, so Task 8 itself doesn't block on this, but the feature isn't usable end to end until Tasks 6/7 land).
- Sequence for execution: Task 2 → Task 4 → Task 1 (needs both) → review findings together → write Task 6 → write Task 7 → Task 3, Task 5, Task 8, Task 9 (independent of the others, can be done in any order alongside).
