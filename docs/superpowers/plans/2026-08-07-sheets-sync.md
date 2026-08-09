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
    "sheet_name": "Offres",
    "reference_sheet_name": "Références",
    "reference_row_b": 2,
    "reference_row_r": 3
  },
```

`reference_sheet_name`/`reference_row_b`/`reference_row_r` point at the dedicated "Références" tab created during the Task 1 spike, which holds template cells for column B's dropdown (row 2) and column R's dropdown (row 3, kept empty by default). Discovered live during the spike, not guessed - see Task 6 for how they're used.

- [ ] **Step 2 (manual): Fill in the real values**

Set `spreadsheet_id` to your **duplicated test sheet's** ID (the long ID in its URL, between `/d/` and `/edit`) — never the real sheet's ID at this stage. Confirm `sheet_name`/`reference_sheet_name` match your actual tab names, and `reference_row_b`/`reference_row_r` match the rows of your "Colonne B dropdown"/"Colonne R dropdown" reference cells (adjust the defaults above if yours differ).

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

### Task 6: `sheets_sync.py` — write new rows' values and column B's formula

Written after live investigation against the duplicated sheet, refined a second time after direct confirmation of the exact business rules. Key facts, verified live rather than guessed:

- Column B (`Traite`) must hold the dropdown validation/colors as configured in the "Références" tab (row 2, `reference_row_b`), with its **value** always driven by the formula `=R{row}<>""` (TRUE when `Raison_exclusion` is non-blank) — never a static default.
- Column R (`Raison_exclusion`) must hold whatever value the import CSV provides (empty, or `"Blacklisté: <term>"` already written by `extract_eml.py`); if empty, the cell must still carry the 6-value dropdown from "Références" (row 3, `reference_row_r`), so the user can classify it manually later.
- The colors on both dropdowns are **not readable via the Sheets API** (confirmed: a fully unrestricted cell read shows no color field anywhere on the validation). They **are** correctly reproduced by `copyPaste` (`pasteType: PASTE_NORMAL`) from the "Références" template cells — confirmed live by inspecting the copied cell and by the user visually confirming the colored chip.
- Writing a plain value afterward via `spreadsheets.values.update` does **not** disturb a cell's validation or formatting, confirmed live: a formula written after a `PASTE_NORMAL` copy left the dropdown validation intact, and the user visually confirmed the colors were still present.
- Sequence that follows from these two facts: copy formatting from "Références" first (`PASTE_NORMAL`, disposable placeholder values), then write every column's final value afterward in one `values.update` call — the final write overwrites the placeholder in B (with the correct formula) and R (with the CSV's value) without touching the formatting/validation copied a moment earlier.
- `output/import_YYYYMMDD.csv`'s column order already matches the sheet's column order (`A..U`) exactly, since both come from `config.json`'s `offres_csv_headers` (now ending in `Message_ID`, column `U`).

**Files:**
- Modify: `sheets_sync.py`
- Test: `tests/test_sheets_sync.py`

**Interfaces:**
- Consumes: `read_import_rows`, `rows_to_sync`, `read_last_synced_id` (Task 4), `check_error_gate`, `write_error_state` (Task 5), `auth.get_credentials` (Task 2), `config["sheets_sync"]["reference_sheet_name"]`/`["reference_row_b"]`/`["reference_row_r"]` (Task 3).
- Produces: `get_sheets_service() -> Resource`, `get_sheet_id(service, spreadsheet_id, sheet_name) -> int`, `get_last_data_row(service, spreadsheet_id, sheet_name) -> int`, `row_values(row, headers, row_number) -> list`, `copy_reference_formatting(service, spreadsheet_id, sheet_id, reference_sheet_id, reference_row, column_index, start_row, end_row) -> None`, `write_new_rows(service, spreadsheet_id, sheet_name, rows, headers, start_row) -> None`, `latest_import_csv(today: str | None = None) -> Path | None`, `run(dry_run: bool) -> None`. `run()` is consumed by Task 7 (which extends its body) and Task 8 (`run_pipeline.py`).

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_sheets_sync.py
import json
from unittest.mock import MagicMock, patch


def test_row_values_orders_by_headers_and_injects_traite_formula():
    row = {"ID": "E000001", "Titre": "Dev", "Traite": "FALSE", "Raison_exclusion": ""}
    headers = ["ID", "Titre", "Traite", "Raison_exclusion"]

    result = row_values(row, headers, row_number=100)

    assert result == ["E000001", "Dev", '=R100<>""', ""]


def test_row_values_defaults_missing_fields_to_empty_string():
    row = {"ID": "E000001", "Traite": "FALSE"}
    headers = ["ID", "Traite", "Message_ID"]

    result = row_values(row, headers, row_number=50)

    assert result == ["E000001", '=R50<>""', ""]


def test_row_values_preserves_raison_exclusion_value():
    row = {"ID": "E000002", "Traite": "FALSE", "Raison_exclusion": "Blacklisté: nounou"}
    headers = ["ID", "Traite", "Raison_exclusion"]

    result = row_values(row, headers, row_number=200)

    assert result == ["E000002", '=R200<>""', "Blacklisté: nounou"]


def test_get_sheet_id_finds_matching_title():
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [
            {"properties": {"sheetId": 0, "title": "Offres"}},
            {"properties": {"sheetId": 558063207, "title": "Références"}},
        ]
    }

    assert get_sheet_id(service, "sheet-id", "Références") == 558063207


def test_get_sheet_id_raises_when_not_found():
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"sheetId": 0, "title": "Offres"}}]
    }

    with pytest.raises(ValueError):
        get_sheet_id(service, "sheet-id", "Nonexistent")


def test_get_last_data_row_counts_column_a_values():
    service = MagicMock()
    values_resource = service.spreadsheets.return_value.values.return_value
    values_resource.get.return_value.execute.return_value = {
        "values": [["ID"], ["E000001"], ["E000002"]]
    }

    assert get_last_data_row(service, "sheet-id", "Offres") == 3


def test_get_last_data_row_returns_one_for_header_only_sheet():
    service = MagicMock()
    values_resource = service.spreadsheets.return_value.values.return_value
    values_resource.get.return_value.execute.return_value = {"values": [["ID"]]}

    assert get_last_data_row(service, "sheet-id", "Offres") == 1


def test_copy_reference_formatting_builds_correct_copypaste_request():
    service = MagicMock()

    copy_reference_formatting(
        service, "sheet-id", sheet_id=0, reference_sheet_id=558063207,
        reference_row=2, column_index=1, start_row=5277, end_row=5279,
    )

    service.spreadsheets.return_value.batchUpdate.assert_called_once_with(
        spreadsheetId="sheet-id",
        body={
            "requests": [{
                "copyPaste": {
                    "source": {
                        "sheetId": 558063207,
                        "startRowIndex": 1, "endRowIndex": 2,
                        "startColumnIndex": 1, "endColumnIndex": 2,
                    },
                    "destination": {
                        "sheetId": 0,
                        "startRowIndex": 5276, "endRowIndex": 5279,
                        "startColumnIndex": 1, "endColumnIndex": 2,
                    },
                    "pasteType": "PASTE_NORMAL",
                }
            }]
        },
    )


def test_copy_reference_formatting_targets_the_given_column():
    service = MagicMock()

    copy_reference_formatting(
        service, "sheet-id", sheet_id=0, reference_sheet_id=558063207,
        reference_row=3, column_index=17, start_row=5277, end_row=5279,
    )

    body = service.spreadsheets.return_value.batchUpdate.call_args.kwargs["body"]
    request = body["requests"][0]["copyPaste"]
    assert request["destination"]["startColumnIndex"] == 17
    assert request["destination"]["endColumnIndex"] == 18


def test_write_new_rows_calls_values_update_with_correct_range_and_formula():
    service = MagicMock()
    headers = ["ID", "Traite"]
    rows = [
        {"ID": "E000010", "Traite": "FALSE"},
        {"ID": "E000011", "Traite": "FALSE"},
    ]

    write_new_rows(service, "sheet-id", "Offres", rows, headers, start_row=100)

    values_resource = service.spreadsheets.return_value.values.return_value
    values_resource.update.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="Offres!A100:B101",
        valueInputOption="USER_ENTERED",
        body={"values": [
            ["E000010", '=R100<>""'],
            ["E000011", '=R101<>""'],
        ]},
    )


def test_write_new_rows_does_nothing_for_empty_list():
    service = MagicMock()

    write_new_rows(service, "sheet-id", "Offres", [], ["ID"], start_row=100)

    service.spreadsheets.return_value.values.return_value.update.assert_not_called()


def test_latest_import_csv_returns_path_when_file_exists(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.OUTPUT_DIR", tmp_path)
    (tmp_path / "import_20260101.csv").write_text("", encoding="utf-8")

    assert latest_import_csv(today="20260101") == tmp_path / "import_20260101.csv"


def test_latest_import_csv_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.OUTPUT_DIR", tmp_path)

    assert latest_import_csv(today="20260101") is None


def _write_sync_config(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "error.json")
    monkeypatch.setattr("sheets_sync.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("sheets_sync.CONFIG_FILE", tmp_path / "config.json")
    (tmp_path / "config.json").write_text(json.dumps({
        "offres_csv_headers": ["ID", "Traite", "Raison_exclusion"],
        "sheets_sync": {
            "spreadsheet_id": "sheet-id", "sheet_name": "Offres",
            "reference_sheet_name": "Références", "reference_row_b": 2, "reference_row_r": 3,
        },
    }), encoding="utf-8")


def _write_import_csv(tmp_path, today: str) -> None:
    import_path = tmp_path / f"import_{today}.csv"
    with import_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ID", "Traite", "Raison_exclusion"], delimiter=";")
        writer.writeheader()
        writer.writerow({"ID": "E000002", "Traite": "FALSE", "Raison_exclusion": ""})


def test_run_dry_run_does_not_write(tmp_path, monkeypatch):
    _write_sync_config(tmp_path, monkeypatch)
    _write_import_csv(tmp_path, "20260101")

    fake_service = MagicMock()
    fake_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
        "values": [["ID"], ["E000001"]]
    }
    with patch("sheets_sync.get_sheets_service", return_value=fake_service):
        run(dry_run=True, today="20260101")

    fake_service.spreadsheets.return_value.values.return_value.update.assert_not_called()
    fake_service.spreadsheets.return_value.batchUpdate.assert_not_called()


def test_run_writes_error_state_on_exception(tmp_path, monkeypatch):
    _write_sync_config(tmp_path, monkeypatch)
    _write_import_csv(tmp_path, "20260101")

    with patch("sheets_sync.get_sheets_service", side_effect=RuntimeError("API quota exceeded")):
        with pytest.raises(RuntimeError):
            run(dry_run=False, today="20260101")

    state = read_error_state()
    assert "API quota exceeded" in state["message"]


def test_run_skips_when_no_import_csv_found(tmp_path, monkeypatch, capsys):
    _write_sync_config(tmp_path, monkeypatch)

    run(dry_run=True, today="20260101")

    assert "Aucun fichier d'import" in capsys.readouterr().out


def test_run_copies_formatting_before_writing_values(tmp_path, monkeypatch):
    """Order matters: copy_reference_formatting must run before
    write_new_rows, or the final values would get overwritten by the
    placeholder from the copy step instead of the other way around."""
    _write_sync_config(tmp_path, monkeypatch)
    _write_import_csv(tmp_path, "20260101")

    call_order = []
    fake_service = MagicMock()
    fake_service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
        "values": [["ID"]]
    }
    fake_service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [
            {"properties": {"sheetId": 0, "title": "Offres"}},
            {"properties": {"sheetId": 558063207, "title": "Références"}},
        ]
    }

    def record_batch_update(**kwargs):
        call_order.append("copy_reference_formatting")
        return MagicMock()

    def record_values_update(**kwargs):
        call_order.append("write_new_rows")
        return MagicMock()

    fake_service.spreadsheets.return_value.batchUpdate.side_effect = record_batch_update
    fake_service.spreadsheets.return_value.values.return_value.update.side_effect = record_values_update

    with patch("sheets_sync.get_sheets_service", return_value=fake_service):
        run(dry_run=False, today="20260101")

    assert call_order == ["copy_reference_formatting", "copy_reference_formatting", "write_new_rows"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sheets_sync.py -v`
Expected: the new tests FAIL (`ImportError`/`AttributeError`/`NameError` for the not-yet-defined names), the 12 tests from Tasks 4-5 still PASS.

- [ ] **Step 3: Add to `sheets_sync.py`**

Add near the top imports:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
```

Add near the other module constants:

```python
LOCAL_TZ = ZoneInfo("Europe/Paris")
```

Add the following functions (after the Task 4/5 functions):

```python
def get_sheets_service():
    creds = auth.get_credentials(scopes=SHEETS_SCOPES, token_file=TOKEN_SHEETS_FILE)
    return build("sheets", "v4", credentials=creds)


def get_sheet_id(service, spreadsheet_id: str, sheet_name: str) -> int:
    """Numeric sheetId for a given tab name."""
    meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties"
    ).execute()
    for sheet in meta["sheets"]:
        if sheet["properties"]["title"] == sheet_name:
            return sheet["properties"]["sheetId"]
    raise ValueError(f"Sheet tab not found: {sheet_name!r}")


def get_last_data_row(service, spreadsheet_id: str, sheet_name: str) -> int:
    """1-indexed sheet row number of the last row containing data (row 1 is
    the header). Returns 1 for a header-only sheet."""
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A:A"
    ).execute()
    return len(result.get("values", []))


def row_values(row: dict, headers: list[str], row_number: int) -> list:
    """Ordered cell values for one CSV row, in the sheet's column order.
    The 'Traite' column is always replaced with the live formula
    '=R{row_number}<>""' instead of the CSV's static default, so it stays
    driven by column R rather than a fixed value."""
    values = [row.get(h, "") for h in headers]
    traite_index = headers.index("Traite")
    values[traite_index] = f'=R{row_number}<>""'
    return values


def copy_reference_formatting(service, spreadsheet_id: str, sheet_id: int,
                               reference_sheet_id: int, reference_row: int,
                               column_index: int, start_row: int, end_row: int) -> None:
    """Copy one column's dropdown validation and colors (plus a disposable
    placeholder value) from a reference cell in the References tab onto
    rows [start_row, end_row] (1-indexed, inclusive) of the given 0-indexed
    column. The placeholder value gets overwritten by write_new_rows() right
    after - a plain values.update never disturbs validation/format,
    confirmed live against the duplicated test sheet."""
    body = {
        "requests": [{
            "copyPaste": {
                "source": {
                    "sheetId": reference_sheet_id,
                    "startRowIndex": reference_row - 1, "endRowIndex": reference_row,
                    "startColumnIndex": 1, "endColumnIndex": 2,
                },
                "destination": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row - 1, "endRowIndex": end_row,
                    "startColumnIndex": column_index, "endColumnIndex": column_index + 1,
                },
                "pasteType": "PASTE_NORMAL",
            }
        }]
    }
    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()


def write_new_rows(service, spreadsheet_id: str, sheet_name: str, rows: list[dict],
                    headers: list[str], start_row: int) -> None:
    """Write the final values for rows into columns A..(last header),
    starting at start_row (1-indexed). Must run AFTER
    copy_reference_formatting for columns B and R, so this write's values
    (including the correct per-row Traite formula) become the final content
    without disturbing the validation/colors copied a moment earlier."""
    if not rows:
        return
    end_row = start_row + len(rows) - 1
    last_col = chr(ord("A") + len(headers) - 1)
    values = [
        row_values(row, headers, row_number=start_row + i)
        for i, row in enumerate(rows)
    ]
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A{start_row}:{last_col}{end_row}",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()


def latest_import_csv(today: str | None = None) -> Path | None:
    """Path to today's output/import_YYYYMMDD.csv, or None if it doesn't
    exist (e.g. extract_eml.py found nothing new to write this run)."""
    if today is None:
        today = datetime.now(LOCAL_TZ).strftime("%Y%m%d")
    path = OUTPUT_DIR / f"import_{today}.csv"
    return path if path.exists() else None


def run(dry_run: bool, today: str | None = None) -> None:
    check_error_gate()

    config = load_config()
    sync_config = config["sheets_sync"]
    spreadsheet_id = sync_config["spreadsheet_id"]
    sheet_name = sync_config["sheet_name"]
    reference_sheet_name = sync_config["reference_sheet_name"]
    reference_row_b = sync_config["reference_row_b"]
    reference_row_r = sync_config["reference_row_r"]
    headers = config["offres_csv_headers"]

    import_csv = latest_import_csv(today=today)
    if import_csv is None:
        print("Aucun fichier d'import a synchroniser aujourd'hui.")
        return

    import_rows = read_import_rows(import_csv)

    try:
        service = get_sheets_service()
        sheet_id = get_sheet_id(service, spreadsheet_id, sheet_name)
        reference_sheet_id = get_sheet_id(service, spreadsheet_id, reference_sheet_name)

        last_synced_id = read_last_synced_id(service, spreadsheet_id, sheet_name)
        new_rows = rows_to_sync(import_rows, last_synced_id)

        if not new_rows:
            print("Aucune nouvelle offre a synchroniser (deja a jour).")
            return

        print(f"{len(new_rows)} nouvelle(s) offre(s) a synchroniser "
              f"(IDs {new_rows[0]['ID']} a {new_rows[-1]['ID']})")

        if dry_run:
            print("[DRY-RUN] Rien ecrit.")
            return

        template_row = get_last_data_row(service, spreadsheet_id, sheet_name)
        start_row = template_row + 1
        end_row = start_row + len(new_rows) - 1

        traite_col_index = headers.index("Traite")
        raison_col_index = headers.index("Raison_exclusion")

        copy_reference_formatting(service, spreadsheet_id, sheet_id, reference_sheet_id,
                                   reference_row_b, traite_col_index, start_row, end_row)
        copy_reference_formatting(service, spreadsheet_id, sheet_id, reference_sheet_id,
                                   reference_row_r, raison_col_index, start_row, end_row)
        write_new_rows(service, spreadsheet_id, sheet_name, new_rows, headers, start_row)

        print(f"{len(new_rows)} offre(s) synchronisee(s) dans {sheet_name} "
              f"(lignes {start_row}-{end_row})")
    except Exception as e:
        write_error_state(str(e))
        raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sheets_sync.py -v`
Expected: 29 passed

- [ ] **Step 5: Commit**

```bash
git add sheets_sync.py tests/test_sheets_sync.py
git commit -m "$(cat <<'EOF'
feat: write new rows and replicate column B/R formatting from References

Modified files:
- sheets_sync.py - copy_reference_formatting, write_new_rows, row_values, latest_import_csv, run(): copies column B and R dropdown validation/colors from the References tab, then writes final values (including the per-row Traite formula) on top - order verified live to preserve formatting
- tests/test_sheets_sync.py - unit tests for all new functions plus a call-order test, Sheets API mocked throughout
EOF
)"
```

- [ ] **Step 6 (manual): Verify live against the duplicated sheet with 2+ rows**

Run `sheets_sync.py` (not `--dry-run`) against the duplicated test sheet with an import CSV containing at least 2 new rows. Visually confirm: each new row's column B shows a working colored dropdown with the correct formula (distinct per row, not all referencing the same source row), column R shows the CSV's value (or the empty dropdown if blank), and setting a row's Raison_exclusion manually (via the dropdown) correctly flips its Traite formula to TRUE.

---

### Task 7: `sheets_sync.py` — extend row-level conditional formatting

Investigation finding: all 4 data-row conditional format rules (alternance/stage highlight, blacklist highlight, duplicate highlight, and the "En cours" highlight) are bounded to the sheet's row count at the time they were last configured — not just the "En cours" one as first suspected. None of them auto-extend to newly appended rows. Per explicit confirmation, "En cours" stays scoped to column A only (not widened to a full row); the other three already span the full column range and keep that scope.

**Files:**
- Modify: `sheets_sync.py`
- Test: `tests/test_sheets_sync.py`

**Interfaces:**
- Consumes: nothing new from earlier tasks beyond what Task 6 already uses.
- Produces: `extend_conditional_format_ranges(service, spreadsheet_id, sheet_id, new_end_row) -> None`. Called by `run()` (extended below) after the write/copy steps from Task 6.

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_sheets_sync.py
def test_extend_conditional_format_ranges_skips_header_rule():
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{
            "properties": {"sheetId": 0},
            "conditionalFormats": [
                {
                    "ranges": [{"startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 26}],
                    "booleanRule": {"condition": {"type": "NOT_BLANK"}, "format": {}},
                },
            ],
        }]
    }

    extend_conditional_format_ranges(service, "sheet-id", sheet_id=0, new_end_row=6000)

    service.spreadsheets.return_value.batchUpdate.assert_not_called()


def test_extend_conditional_format_ranges_updates_data_row_rules():
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{
            "properties": {"sheetId": 0},
            "conditionalFormats": [
                {
                    "ranges": [{"startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 26}],
                    "booleanRule": {"condition": {"type": "NOT_BLANK"}, "format": {}},
                },
                {
                    "ranges": [{"startRowIndex": 1, "endRowIndex": 5276, "startColumnIndex": 0, "endColumnIndex": 26}],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": '=$H2<>""'}]},
                        "format": {"backgroundColor": {"red": 1, "green": 0.9490196, "blue": 0.8}},
                    },
                },
                {
                    "ranges": [{"startRowIndex": 1, "endRowIndex": 3625, "startColumnIndex": 0, "endColumnIndex": 1}],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": '=($B2="En cours")'}]},
                        "format": {"backgroundColor": {"red": 0.40392157, "green": 0.30588236, "blue": 0.654902}},
                    },
                },
            ],
        }]
    }

    extend_conditional_format_ranges(service, "sheet-id", sheet_id=0, new_end_row=6000)

    body = service.spreadsheets.return_value.batchUpdate.call_args.kwargs["body"]
    requests = body["requests"]
    assert len(requests) == 2  # header rule (index 0) skipped, 2 data-row rules updated

    duplicate_update = requests[0]["updateConditionalFormatRule"]
    assert duplicate_update["sheetId"] == 0
    assert duplicate_update["index"] == 1
    assert duplicate_update["rule"]["ranges"][0]["endRowIndex"] == 6000
    assert duplicate_update["rule"]["ranges"][0]["startColumnIndex"] == 0
    assert duplicate_update["rule"]["ranges"][0]["endColumnIndex"] == 26
    assert duplicate_update["rule"]["booleanRule"]["condition"]["values"][0]["userEnteredValue"] == '=$H2<>""'

    en_cours_update = requests[1]["updateConditionalFormatRule"]
    assert en_cours_update["index"] == 2
    assert en_cours_update["rule"]["ranges"][0]["endRowIndex"] == 6000
    assert en_cours_update["rule"]["ranges"][0]["startColumnIndex"] == 0
    assert en_cours_update["rule"]["ranges"][0]["endColumnIndex"] == 1  # column A only, unchanged


def test_extend_conditional_format_ranges_does_nothing_when_no_rules():
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"sheetId": 0}, "conditionalFormats": []}]
    }

    extend_conditional_format_ranges(service, "sheet-id", sheet_id=0, new_end_row=6000)

    service.spreadsheets.return_value.batchUpdate.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sheets_sync.py -v`
Expected: the 3 new tests FAIL (`NameError: name 'extend_conditional_format_ranges' is not defined`), the 29 from Task 6 still PASS.

- [ ] **Step 3: Add to `sheets_sync.py`**

```python
def extend_conditional_format_ranges(service, spreadsheet_id: str, sheet_id: int,
                                      new_end_row: int) -> None:
    """Extend every data-row conditional format rule's endRowIndex to
    new_end_row (0-indexed, exclusive - the sheet's new total row count
    after appending). The header-row highlight (starts at row 0) is left
    untouched. Each rule's column scope (e.g. 'En cours' limited to column
    A) is preserved exactly as configured - only endRowIndex changes."""
    meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties.sheetId,conditionalFormats)",
    ).execute()
    sheet = next(s for s in meta["sheets"] if s["properties"]["sheetId"] == sheet_id)
    rules = sheet.get("conditionalFormats", [])

    requests = []
    for index, rule in enumerate(rules):
        ranges = rule.get("ranges", [])
        if not ranges or ranges[0].get("startRowIndex", 0) == 0:
            continue
        updated_rule = json.loads(json.dumps(rule))
        for r in updated_rule["ranges"]:
            r["endRowIndex"] = new_end_row
        requests.append({
            "updateConditionalFormatRule": {
                "sheetId": sheet_id,
                "index": index,
                "rule": updated_rule,
            }
        })

    if requests:
        service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests}).execute()
```

- [ ] **Step 4: Modify `run()` to call it after the write step**

In `sheets_sync.py`'s `run()` function, replace:

```python
        copy_reference_formatting(service, spreadsheet_id, sheet_id, reference_sheet_id,
                                   reference_row_b, traite_col_index, start_row, end_row)
        copy_reference_formatting(service, spreadsheet_id, sheet_id, reference_sheet_id,
                                   reference_row_r, raison_col_index, start_row, end_row)
        write_new_rows(service, spreadsheet_id, sheet_name, new_rows, headers, start_row)

        print(f"{len(new_rows)} offre(s) synchronisee(s) dans {sheet_name} "
              f"(lignes {start_row}-{end_row})")
```

with:

```python
        copy_reference_formatting(service, spreadsheet_id, sheet_id, reference_sheet_id,
                                   reference_row_b, traite_col_index, start_row, end_row)
        copy_reference_formatting(service, spreadsheet_id, sheet_id, reference_sheet_id,
                                   reference_row_r, raison_col_index, start_row, end_row)
        write_new_rows(service, spreadsheet_id, sheet_name, new_rows, headers, start_row)
        extend_conditional_format_ranges(service, spreadsheet_id, sheet_id, new_end_row=end_row)

        print(f"{len(new_rows)} offre(s) synchronisee(s) dans {sheet_name} "
              f"(lignes {start_row}-{end_row})")
```

- [ ] **Step 5: Run tests to verify everything passes**

Run: `pytest tests/test_sheets_sync.py -v`
Expected: 32 passed

- [ ] **Step 6: Commit**

```bash
git add sheets_sync.py tests/test_sheets_sync.py
git commit -m "$(cat <<'EOF'
feat: extend conditional formatting ranges on sync

Modified files:
- sheets_sync.py - extend_conditional_format_ranges() extends all data-row conditional format rules to cover newly synced rows, wired into run(); the range-clipping problem the user described applies to all 4 data-row rules, not just "En cours"
- tests/test_sheets_sync.py - tests covering header-rule skip, endRowIndex extension, column-scope preservation, and the no-rules edge case
EOF
)"
```

- [ ] **Step 7 (manual): Verify live and visually confirm formatting extends correctly**

Run `sheets_sync.py` against the duplicated test sheet again (real run, not `--dry-run`) with new rows to sync, then visually check the sheet: new rows should show correct duplicate/blacklist/alternance highlighting where applicable, and manually setting one new row's column B to `"En cours"` should show the dark purple highlight in column A only.

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

- Tasks 2, 3, 4, 5, 8, 9 are fully automatable.
- Task 1 required the user's direct participation (running the spike script against the duplicated sheet, reviewing its output) - completed, see the plan's originating conversation for the full investigation trail.
- Tasks 6 and 7 are now fully specified, based on Task 1's live findings plus a second live round of investigation into the exact write ordering needed to preserve dropdown colors (copy formatting from References first, write final values second - confirmed live that a plain values.update after a copyPaste does not disturb validation/formatting).
- Remaining sequence: Task 3 → Task 5 → Task 6 (needs Task 3's config) → Task 7 (extends Task 6's `run()`) → Task 8 → Task 9. Tasks 3 and 5 have no dependency on each other and could be done in either order.
