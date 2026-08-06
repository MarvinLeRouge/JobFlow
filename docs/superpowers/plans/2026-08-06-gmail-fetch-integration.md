# Gmail Fetch Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate `.eml` retrieval from Gmail via the Gmail API and integrate it into the existing `rename_eml.py` → `extract_eml.py` pipeline, replacing the CSV-based `eml_index.csv` with a unified JSON ledger shared by all three steps.

**Architecture:** Three scripts (`fetch_gmail.py` new, `rename_eml.py` and `extract_eml.py` modified) share two new modules — `providers.py` (sender domain → folder routing) and `ledger.py` (load/save `logs/email_ledger.json`) — and are chained by a new `run_pipeline.py` orchestrator. `output/offres.csv` gains a `Message_ID` column for offer → source-email traceability.

**Tech Stack:** Python 3.13, `google-api-python-client` / `google-auth-oauthlib` (Gmail API + OAuth2), `pytest`, `ruff` + `ruff-format`, `pre-commit`.

## Global Constraints

- CSV separator `;`, UTF-8 encoding, everywhere (existing project convention, from `config/config.json`).
- `token.json` and OAuth client credentials (`credentials.json`) are never committed — must be in `.gitignore` before Task 9.
- No new column may shift the position of existing `offres.csv` columns — the live Google Sheet's conditional formatting references fixed column letters (`$H2`, `$T2`). New columns are always appended at the end.
- Code, comments, commit messages: English. `README.md` is English, `README.fr.md` is French, kept in sync.
- No placeholder/TODO code. No new external service calls in unit tests — Gmail API interactions are mocked.
- Every task that touches `sources/`, `logs/`, `output/`, or `config/` in a test must use `tmp_path`/`monkeypatch` — never the real project data.

---

### Task 1: Project tooling (ruff, pytest, pre-commit)

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.pre-commit-config.yaml`
- Modify: `.gitignore`

**Interfaces:**
- Produces: a working `pytest` (importing project-root modules directly, no package install needed) and `ruff`/`ruff-format` setup that every later task's tests and code must satisfy.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: Write `requirements.txt`**

```
google-api-python-client>=2.100
google-auth-oauthlib>=1.2
google-auth-httplib2>=0.2
requests>=2.31
```

- [ ] **Step 3: Write `requirements-dev.txt`**

```
-r requirements.txt
pytest>=8.0
ruff>=0.6
pre-commit>=3.7
```

- [ ] **Step 4: Create a venv and install dev dependencies**

Run: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`
Expected: install completes with no errors.

- [ ] **Step 5: Verify pytest runs (even with zero tests yet)**

Run: `.venv/bin/pytest`
Expected: `collected 0 items` (no errors — confirms `pythonpath` config resolves).

- [ ] **Step 6: Verify ruff runs**

Run: `.venv/bin/ruff check .`
Expected: exits cleanly (existing scripts may report style issues — that's fine, don't fix pre-existing code in this task).

- [ ] **Step 7: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

- [ ] **Step 8: Install the hook and verify it runs**

Run: `.venv/bin/pre-commit install && .venv/bin/pre-commit run --all-files`
Expected: hook executes (may reformat/report on existing files — that's expected on first run).

- [ ] **Step 9: Update `.gitignore`**

Append to the existing `.gitignore`:

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
token.json
credentials.json
client_secret*.json
```

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml requirements.txt requirements-dev.txt .pre-commit-config.yaml .gitignore
git commit -m "chore: add pytest/ruff/pre-commit tooling"
```

---

### Task 2: `providers.py` shared module

**Files:**
- Create: `providers.py`
- Test: `tests/test_providers.py`

**Interfaces:**
- Produces: `load_domain_map(patterns_file: Path) -> dict[str, str]`, `sender_domain(from_header: str) -> str`, `expected_folder(domain: str, domain_map: dict) -> str | None`. Consumed by Task 3 (`rename_eml.py`) and Task 10 (`fetch_gmail.py`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_providers.py
import json
from pathlib import Path

import pytest

from providers import expected_folder, load_domain_map, sender_domain


@pytest.fixture
def patterns_file(tmp_path: Path) -> Path:
    data = {
        "_comment": "ignored",
        "indeed_alerte": {
            "folder": "indeed",
            "sender_domains": ["jobalert.indeed.com", "indeed.com"],
        },
        "linkedin": {
            "folder": "linkedin",
            "sender_domains": ["linkedin.com"],
        },
    }
    path = tmp_path / "scraping_patterns.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_domain_map_builds_domain_to_folder_mapping(patterns_file):
    mapping = load_domain_map(patterns_file)
    assert mapping == {
        "jobalert.indeed.com": "indeed",
        "indeed.com": "indeed",
        "linkedin.com": "linkedin",
    }


def test_load_domain_map_missing_file_returns_empty_dict(tmp_path):
    assert load_domain_map(tmp_path / "does_not_exist.json") == {}


def test_sender_domain_extracts_domain_from_from_header():
    assert sender_domain("Foo Bar <foo@jobalert.indeed.com>") == "jobalert.indeed.com"


def test_sender_domain_returns_empty_string_when_no_match():
    assert sender_domain("not an email") == ""


def test_expected_folder_matches_exact_domain(patterns_file):
    mapping = load_domain_map(patterns_file)
    assert expected_folder("jobalert.indeed.com", mapping) == "indeed"


def test_expected_folder_falls_back_to_parent_suffix(patterns_file):
    mapping = load_domain_map(patterns_file)
    assert expected_folder("sub.linkedin.com", mapping) == "linkedin"


def test_expected_folder_unknown_domain_returns_none(patterns_file):
    mapping = load_domain_map(patterns_file)
    assert expected_folder("unknown.example.com", mapping) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_providers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'providers'`

- [ ] **Step 3: Write `providers.py`**

```python
"""Shared sender-domain routing: maps an email's sender domain to its
provider folder under sources/, using config/scraping_patterns.json."""

import json
import re
from pathlib import Path


def load_domain_map(patterns_file: Path) -> dict:
    """Build {sender_domain: expected_folder} from scraping_patterns.json."""
    if not patterns_file.exists():
        return {}
    with patterns_file.open(encoding="utf-8") as f:
        patterns = json.load(f)
    mapping = {}
    for key, p in patterns.items():
        if key.startswith("_"):
            continue
        folder = p.get("folder")
        for domain in p.get("sender_domains", []):
            if domain and folder:
                mapping[domain.lower()] = folder
    return mapping


def sender_domain(from_header: str) -> str:
    """Extract the domain from a From: header, e.g. 'Foo <bar@baz.com>' -> 'baz.com'."""
    match = re.search(r"@([\w.\-]+)", from_header or "")
    return match.group(1).lower() if match else ""


def expected_folder(domain: str, domain_map: dict) -> str | None:
    """Find the expected folder for this domain, testing the full domain
    then parent suffixes (e.g. 'jobalert.indeed.com' -> 'indeed.com' -> 'com')."""
    parts = domain.split(".")
    for i in range(len(parts)):
        candidate = ".".join(parts[i:])
        if candidate in domain_map:
            return domain_map[candidate]
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_providers.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add providers.py tests/test_providers.py
git commit -m "feat: add providers module for sender domain routing"
```

---

### Task 3: Refactor `rename_eml.py` to use `providers.py`

Pure extraction, no behavior change: `load_domain_map()`, `sender_domain()`, `expected_folder()` currently defined inline in `rename_eml.py` (lines 49–86 of the current file) are removed and imported from Task 2's module instead. The CSV-based index (`eml_index.csv`) is untouched here — that changes in Task 7.

**Files:**
- Modify: `rename_eml.py`

**Interfaces:**
- Consumes: `providers.load_domain_map`, `providers.sender_domain`, `providers.expected_folder` (Task 2).

- [ ] **Step 1: Remove the inline functions and import from `providers`**

In `rename_eml.py`, delete the `load_domain_map()`, `sender_domain()`, and `expected_folder()` function definitions (the `# ── Config helpers` section), and add near the top imports:

```python
from providers import expected_folder, load_domain_map, sender_domain
```

- [ ] **Step 2: Update the call site in `check_folders()`**

Change:

```python
    domain_map = load_domain_map()
```

to:

```python
    domain_map = load_domain_map(PATTERNS_FILE)
```

- [ ] **Step 3: Verify behavior is unchanged**

Run: `python3 rename_eml.py --check`
Expected: completes without error, same output structure as before this change (mismatch/unknown/OK counts reflecting your actual `sources/` content — no regression, since this is a pure extraction with no logic change).

- [ ] **Step 4: Commit**

```bash
git add rename_eml.py
git commit -m "refactor: extract domain routing into providers module"
```

---

### Task 4: `ledger.py` shared module

**Files:**
- Create: `ledger.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- Produces: `load_ledger(path: Path) -> dict`, `save_ledger(path: Path, ledger: dict) -> None`. Consumed by Task 5, Task 7, Task 8, Task 10.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ledger.py
import json

from ledger import load_ledger, save_ledger


def test_load_ledger_missing_file_returns_empty_dict(tmp_path):
    assert load_ledger(tmp_path / "email_ledger.json") == {}


def test_save_then_load_ledger_round_trips(tmp_path):
    path = tmp_path / "logs" / "email_ledger.json"
    ledger = {
        "<msg-1>": {
            "gmail_id": "abc123",
            "fichier": "indeed/20260806-1032-foo.eml",
            "date_email": "2026-08-06T10:32:00+0200",
            "fetched_at": "2026-08-06T10:35:12Z",
            "indexed_at": "2026-08-06T10:35:12Z",
            "statut_extraction": "PENDING",
        }
    }
    save_ledger(path, ledger)
    assert load_ledger(path) == ledger


def test_save_ledger_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "logs" / "email_ledger.json"
    save_ledger(path, {})
    assert path.exists()


def test_save_ledger_writes_valid_json(tmp_path):
    path = tmp_path / "email_ledger.json"
    save_ledger(path, {"<msg-1>": {"gmail_id": "before_gmail_api"}})
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    assert data == {"<msg-1>": {"gmail_id": "before_gmail_api"}}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ledger.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ledger'`

- [ ] **Step 3: Write `ledger.py`**

```python
"""Shared read/write access to logs/email_ledger.json, the per-email
tracking ledger used by fetch_gmail.py, rename_eml.py and extract_eml.py."""

import json
from pathlib import Path


def load_ledger(path: Path) -> dict:
    """Return the ledger as {message_id: record}. Empty dict if the file
    doesn't exist yet."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_ledger(path: Path, ledger: dict) -> None:
    """Persist the ledger as JSON, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2, sort_keys=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ledger.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add ledger.py tests/test_ledger.py
git commit -m "feat: add ledger module for email_ledger.json read/write"
```

---

### Task 5: Migration script — `eml_index.csv` → `email_ledger.json`

One-shot script. Does **not** delete `logs/eml_index.csv` — per project safety rules, files are never deleted without explicit user confirmation. The user removes it manually once the migration is verified.

**Files:**
- Create: `migrate_eml_index_to_ledger.py`
- Test: `tests/test_migrate_eml_index_to_ledger.py`

**Interfaces:**
- Consumes: `ledger.save_ledger` (Task 4).
- Produces: `build_ledger_from_csv(csv_path: Path) -> dict`, `BEFORE_GMAIL_API = "before_gmail_api"` (referenced by Task 7's tests as the expected sentinel).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_migrate_eml_index_to_ledger.py
import csv
from pathlib import Path

from migrate_eml_index_to_ledger import BEFORE_GMAIL_API, build_ledger_from_csv


def _write_index_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def test_build_ledger_from_csv_maps_fields(tmp_path):
    csv_path = tmp_path / "eml_index.csv"
    _write_index_csv(
        csv_path,
        ["Message-ID", "Fichier", "Date_email", "Date_indexation", "Statut_extraction"],
        [{
            "Message-ID": "<msg-1>",
            "Fichier": "indeed/20260806-1032-foo.eml",
            "Date_email": "2026-08-06T10:32:00+0200",
            "Date_indexation": "2026-08-06T10:35:00Z",
            "Statut_extraction": "OK",
        }],
    )

    ledger = build_ledger_from_csv(csv_path)

    assert ledger == {
        "<msg-1>": {
            "gmail_id": BEFORE_GMAIL_API,
            "fichier": "indeed/20260806-1032-foo.eml",
            "date_email": "2026-08-06T10:32:00+0200",
            "fetched_at": "2026-08-06T10:35:00Z",
            "indexed_at": "2026-08-06T10:35:00Z",
            "statut_extraction": "OK",
        }
    }


def test_build_ledger_from_csv_defaults_missing_statut_to_pending(tmp_path):
    csv_path = tmp_path / "eml_index.csv"
    _write_index_csv(
        csv_path,
        ["Message-ID", "Fichier", "Date_email", "Date_indexation"],
        [{
            "Message-ID": "<msg-2>",
            "Fichier": "linkedin/20260601-0900-bar.eml",
            "Date_email": "2026-06-01T09:00:00+0200",
            "Date_indexation": "2026-06-01T09:05:00Z",
        }],
    )

    ledger = build_ledger_from_csv(csv_path)

    assert ledger["<msg-2>"]["statut_extraction"] == "PENDING"
    assert ledger["<msg-2>"]["gmail_id"] == BEFORE_GMAIL_API


def test_build_ledger_from_csv_missing_file_returns_empty_dict(tmp_path):
    assert build_ledger_from_csv(tmp_path / "does_not_exist.csv") == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_migrate_eml_index_to_ledger.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'migrate_eml_index_to_ledger'`

- [ ] **Step 3: Write `migrate_eml_index_to_ledger.py`**

```python
#!/usr/bin/env python3
"""One-shot migration: converts logs/eml_index.csv into logs/email_ledger.json.

Run once, after upgrading to the unified ledger. Does not delete the old
eml_index.csv — remove it manually once you've confirmed the migration.

Usage:
    python3 migrate_eml_index_to_ledger.py [--dry-run]
"""

import argparse
import csv
from pathlib import Path

from ledger import save_ledger

ROOT = Path(__file__).parent
LOGS_DIR = ROOT / "logs"
INDEX_CSV = LOGS_DIR / "eml_index.csv"
LEDGER_JSON = LOGS_DIR / "email_ledger.json"

BEFORE_GMAIL_API = "before_gmail_api"


def build_ledger_from_csv(csv_path: Path) -> dict:
    """Read the legacy eml_index.csv and return the equivalent ledger dict."""
    if not csv_path.exists():
        return {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    ledger = {}
    for row in rows:
        message_id = row["Message-ID"]
        indexed_at = row.get("Date_indexation", "")
        ledger[message_id] = {
            "gmail_id": BEFORE_GMAIL_API,
            "fichier": row.get("Fichier", ""),
            "date_email": row.get("Date_email", ""),
            "fetched_at": indexed_at,
            "indexed_at": indexed_at,
            "statut_extraction": row.get("Statut_extraction") or "PENDING",
        }
    return ledger


def main(dry_run: bool) -> None:
    ledger = build_ledger_from_csv(INDEX_CSV)
    print(f"{len(ledger)} entrée(s) migrée(s) depuis {INDEX_CSV.name}")
    if dry_run:
        print("[DRY-RUN] Rien écrit.")
        return
    if LEDGER_JSON.exists():
        print(f"ERREUR : {LEDGER_JSON} existe déjà, migration abandonnée.")
        raise SystemExit(1)
    save_ledger(LEDGER_JSON, ledger)
    print(f"Ledger écrit : {LEDGER_JSON}")
    print(f"NOTE : {INDEX_CSV} n'a pas été supprimé — à retirer manuellement une fois vérifié.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_migrate_eml_index_to_ledger.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add migrate_eml_index_to_ledger.py tests/test_migrate_eml_index_to_ledger.py
git commit -m "feat: add one-shot migration from eml_index.csv to email_ledger.json"
```

- [ ] **Step 6: Run the real migration against project data**

Run: `python3 migrate_eml_index_to_ledger.py --dry-run` then, once the entry count looks right (matches your current `logs/eml_index.csv` row count), `python3 migrate_eml_index_to_ledger.py`
Expected: `logs/email_ledger.json` created with one entry per historical row, `gmail_id` = `"before_gmail_api"` throughout.

---

### Task 6: Migration script — add `Message_ID` column to `offres.csv`

**Files:**
- Create: `migrate_offres_add_message_id.py`
- Test: `tests/test_migrate_offres_add_message_id.py`
- Modify: `config/config.json` (via running the script, not by hand)

**Interfaces:**
- Produces: `add_message_id_column(rows: list[dict], headers: list[str]) -> tuple[list[dict], list[str]]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_migrate_offres_add_message_id.py
from migrate_offres_add_message_id import NEW_COLUMN, add_message_id_column


def test_add_message_id_column_appends_at_end():
    headers = ["ID", "Traite", "Notes"]
    rows = [{"ID": "E000001", "Traite": "FALSE", "Notes": ""}]

    new_rows, new_headers = add_message_id_column(rows, headers)

    assert new_headers == ["ID", "Traite", "Notes", "Message_ID"]
    assert new_rows == [{"ID": "E000001", "Traite": "FALSE", "Notes": "", "Message_ID": ""}]


def test_add_message_id_column_is_idempotent():
    headers = ["ID", "Message_ID"]
    rows = [{"ID": "E000001", "Message_ID": "<msg-1>"}]

    new_rows, new_headers = add_message_id_column(rows, headers)

    assert new_headers == headers
    assert new_rows == rows


def test_add_message_id_column_handles_empty_rows():
    new_rows, new_headers = add_message_id_column([], ["ID"])
    assert new_rows == []
    assert new_headers == ["ID", NEW_COLUMN]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_migrate_offres_add_message_id.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'migrate_offres_add_message_id'`

- [ ] **Step 3: Write `migrate_offres_add_message_id.py`**

```python
#!/usr/bin/env python3
"""One-shot migration: adds an empty Message_ID column to output/offres.csv
and appends "Message_ID" to config/config.json's offres_csv_headers.

Message_ID is appended at the END of the header list (not inserted), so
existing column letters (A..T) referenced by the Google Sheets conditional
formatting formulas stay unchanged.

Usage:
    python3 migrate_offres_add_message_id.py [--dry-run]
"""

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "config" / "config.json"
OFFRES_CSV = ROOT / "output" / "offres.csv"

NEW_COLUMN = "Message_ID"


def add_message_id_column(rows: list[dict], headers: list[str]) -> tuple[list[dict], list[str]]:
    """Return (rows, headers) with Message_ID appended if not already present."""
    if NEW_COLUMN in headers:
        return rows, headers
    new_headers = [*headers, NEW_COLUMN]
    new_rows = [{**row, NEW_COLUMN: ""} for row in rows]
    return new_rows, new_headers


def main(dry_run: bool) -> None:
    with CONFIG_FILE.open(encoding="utf-8") as f:
        config = json.load(f)
    headers = config["offres_csv_headers"]

    if OFFRES_CSV.exists():
        with OFFRES_CSV.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
    else:
        rows = []

    new_rows, new_headers = add_message_id_column(rows, headers)

    print(f"{len(new_rows)} ligne(s) dans {OFFRES_CSV.name}")
    if new_headers == headers:
        print(f"{NEW_COLUMN} déjà présent, rien à faire.")
        return

    if dry_run:
        print(f"[DRY-RUN] Ajouterait la colonne {NEW_COLUMN} (position {len(new_headers)}).")
        return

    config["offres_csv_headers"] = new_headers
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")

    if OFFRES_CSV.exists():
        with OFFRES_CSV.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=new_headers, delimiter=";")
            writer.writeheader()
            writer.writerows(new_rows)

    print(f"{CONFIG_FILE.name} et {OFFRES_CSV.name} mis à jour avec la colonne {NEW_COLUMN}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_migrate_offres_add_message_id.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add migrate_offres_add_message_id.py tests/test_migrate_offres_add_message_id.py
git commit -m "feat: add one-shot migration adding Message_ID to offres.csv"
```

- [ ] **Step 6: Run the real migration against project data**

Run: `python3 migrate_offres_add_message_id.py --dry-run` then `python3 migrate_offres_add_message_id.py`
Expected: `config/config.json`'s `offres_csv_headers` ends with `"Message_ID"`; `output/offres.csv` has a new empty last column on every row.

---

### Task 7: Rewrite `rename_eml.py` to use the ledger

Replaces the CSV-based index with `email_ledger.json`. Introduces `resolve_action()`, a pure function extracted specifically to make the "rename vs. reindex vs. duplicate" decision unit-testable without touching the filesystem — this decision logic changes behavior (see rationale below) so it needs its own tests, unlike Task 3's pure refactor.

**Rationale for the behavior change:** previously, "Message-ID already in the index" always meant "already fully processed" (index and rename happened atomically). Once `fetch_gmail.py` (Task 10) can create a ledger entry *before* the file is renamed, that assumption breaks — a freshly-fetched file would be seen as "already indexed" and never get its `yyyymmdd-hhmm-` prefix. `resolve_action()` fixes this by checking the filename prefix independently of ledger presence, and treating a ledger hit with a matching `fichier` path as "still needs renaming, just update the entry" rather than "nothing to do."

**Files:**
- Modify: `rename_eml.py`
- Test: `tests/test_rename_eml.py`

**Interfaces:**
- Consumes: `ledger.load_ledger`, `ledger.save_ledger` (Task 4).
- Produces: `resolve_action(mid: str, rel: Path, filename: str, ledger: dict) -> str` (returns `"duplicate"`, `"reindex"`, or `"rename"`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rename_eml.py
from pathlib import Path

from rename_eml import resolve_action


def test_resolve_action_new_message_id_needs_rename():
    assert resolve_action("<msg-1>", Path("indeed/raw.eml"), "raw.eml", {}) == "rename"


def test_resolve_action_new_message_id_already_prefixed():
    action = resolve_action(
        "<msg-1>", Path("indeed/20260806-1032-raw.eml"), "20260806-1032-raw.eml", {}
    )
    assert action == "reindex"


def test_resolve_action_known_message_id_same_file_not_yet_renamed():
    ledger = {"<msg-1>": {"fichier": "indeed/abc123-raw.eml"}}
    action = resolve_action("<msg-1>", Path("indeed/abc123-raw.eml"), "abc123-raw.eml", ledger)
    assert action == "rename"


def test_resolve_action_known_message_id_same_file_already_renamed():
    ledger = {"<msg-1>": {"fichier": "indeed/20260806-1032-raw.eml"}}
    action = resolve_action(
        "<msg-1>", Path("indeed/20260806-1032-raw.eml"), "20260806-1032-raw.eml", ledger
    )
    assert action == "reindex"


def test_resolve_action_known_message_id_different_file_is_duplicate():
    ledger = {"<msg-1>": {"fichier": "indeed/20260601-0900-other.eml"}}
    action = resolve_action("<msg-1>", Path("indeed/raw.eml"), "raw.eml", ledger)
    assert action == "duplicate"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rename_eml.py -v`
Expected: FAIL — `resolve_action` not defined (or the whole module fails to import if earlier steps aren't done yet; that's fine, do Step 3 next).

- [ ] **Step 3: Modify `rename_eml.py`**

Replace the module-level constants block (`INDEX_FILE`, `INDEX_FIELDS`) — remove those two, add:

```python
from ledger import load_ledger, save_ledger

LEDGER_FILE = LOGS_DIR / "email_ledger.json"
```

Remove the `load_index()` and `save_index()` functions entirely (the `# ── Index helpers` section).

Add the new `resolve_action()` function (place it near `build_new_name`/`resolve_collision`):

```python
def resolve_action(mid: str, rel: Path, filename: str, ledger: dict) -> str:
    """Decide what to do with this file: 'duplicate' (a different file is
    already indexed under this Message-ID), 'reindex' (correctly named
    already, just refresh the ledger entry), or 'rename' (needs the
    yyyymmdd-hhmm- prefix, then the ledger entry is created/updated)."""
    entry = ledger.get(mid)
    if entry is not None and entry.get("fichier") != str(rel):
        return "duplicate"
    if DATE_PREFIX_RE.match(filename):
        return "reindex"
    return "rename"
```

Replace the entire `run()` function with:

```python
def run(dry_run: bool, purge: bool):

    if purge:
        if not DUPES_DIR.exists() or not any(DUPES_DIR.iterdir()):
            print("sources/_duplicates/ est vide ou absent — rien à purger.")
            return
        files = sorted(DUPES_DIR.iterdir())
        print(f"{'[DRY-RUN] ' if dry_run else ''}Purge de {len(files)} fichier(s) dans _duplicates/")
        for f in files:
            print(f"  DEL {f.name}")
            if not dry_run:
                f.unlink()
        if not dry_run:
            print("Purge terminée.")
        return

    eml_files = sorted(
        f for f in SOURCES_DIR.rglob("*.eml")
        if DUPES_DIR not in f.parents and TESTS_DIR not in f.parents
    )

    if not eml_files:
        print("Aucun fichier .eml trouvé dans sources/ (hors _duplicates/).")
        return

    tag = "[DRY-RUN] " if dry_run else ""
    print(f"{tag}{len(eml_files)} fichier(s) .eml trouvé(s)\n")

    ledger = load_ledger(LEDGER_FILE)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    renamed = duped = skipped = errors = 0

    for eml_path in eml_files:
        rel = eml_path.relative_to(SOURCES_DIR)
        mid, dt = parse_headers(eml_path)

        if mid is None:
            print(f"  SKIP (Message-ID introuvable) : {rel}")
            errors += 1
            continue

        action = resolve_action(mid, rel, eml_path.name, ledger)
        entry = ledger.get(mid, {})

        if action == "duplicate":
            DUPES_DIR.mkdir(parents=True, exist_ok=True)
            dest = DUPES_DIR / eml_path.name
            counter = 2
            while dest.exists():
                dest = DUPES_DIR / f"{eml_path.stem}_{counter}.eml"
                counter += 1
            print(f"  DUP  {rel}\n       → _duplicates/{dest.name}")
            print(f"       (déjà indexé comme : {entry.get('fichier')})")
            if not dry_run:
                shutil.move(str(eml_path), dest)
            duped += 1
            continue

        date_str = dt.strftime("%Y-%m-%dT%H:%M:%S%z") if dt else ""

        if action == "reindex":
            print(f"  IDX  (déjà préfixé) : {rel}")
            if not dry_run:
                ledger[mid] = {
                    "gmail_id": entry.get("gmail_id", "manual"),
                    "fichier": str(rel),
                    "date_email": date_str,
                    "fetched_at": entry.get("fetched_at", now_str),
                    "indexed_at": now_str,
                    "statut_extraction": entry.get("statut_extraction", "PENDING"),
                }
            skipped += 1
            continue

        # action == "rename"
        if dt is None:
            print(f"  SKIP (date introuvable) : {rel}")
            errors += 1
            continue

        new_path = resolve_collision(eml_path, dt, eml_path.stem)
        rel_new = new_path.relative_to(SOURCES_DIR)
        print(f"  REN  {rel}\n       → {rel_new}")

        if not dry_run:
            eml_path.rename(new_path)
            ledger[mid] = {
                "gmail_id": entry.get("gmail_id", "manual"),
                "fichier": str(rel_new),
                "date_email": date_str,
                "fetched_at": entry.get("fetched_at", now_str),
                "indexed_at": now_str,
                "statut_extraction": entry.get("statut_extraction", "PENDING"),
            }
        renamed += 1

    if not dry_run:
        save_ledger(LEDGER_FILE, ledger)
        print(f"\nLedger mis à jour : {len(ledger)} entrée(s) → {LEDGER_FILE}")

    print(f"\n{'Simulation' if dry_run else 'Résultat'} : "
          f"{renamed} renommé(s), {duped} doublon(s) → _duplicates/, "
          f"{skipped} déjà préfixés/réindexés, {errors} erreur(s).")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rename_eml.py -v`
Expected: 5 passed

- [ ] **Step 5: Verify against real project data**

Run: `python3 rename_eml.py --dry-run`
Expected: completes without error; every file reports `skipped` (via `reindex`, since they're all already prefixed and now present in `email_ledger.json` from Task 5's migration) — 0 unexpected `rename`/`duplicate` actions.

- [ ] **Step 6: Commit**

```bash
git add rename_eml.py tests/test_rename_eml.py
git commit -m "feat: switch rename_eml.py to the unified email ledger"
```

---

### Task 8: Rewrite `extract_eml.py` to use the ledger

Same ledger swap as Task 7, plus the new `Message_ID` field on every output row (available now that Task 6 added the column). The extraction logic itself (all `extract_*` functions, dedup, blacklist, stack detection) is untouched.

**Files:**
- Modify: `extract_eml.py`

**Interfaces:**
- Consumes: `ledger.load_ledger`, `ledger.save_ledger` (Task 4).

- [ ] **Step 1: Update module-level constants and imports**

Replace:

```python
EML_INDEX     = LOGS_DIR / "eml_index.csv"
```

with:

```python
LEDGER_FILE   = LOGS_DIR / "email_ledger.json"
```

Add near the top imports:

```python
from ledger import load_ledger, save_ledger
```

- [ ] **Step 2: Remove `load_eml_index()` and `save_eml_index()`**

Delete the `# ── Gestion index EML` section (both functions) — replaced by direct `load_ledger`/`save_ledger` calls in `main()`.

- [ ] **Step 3: Replace `main()`**

```python
def main(dry_run: bool, force_headers: bool | None = None):
    """
    force_headers :
      None  → automatique : headers si aucun import_*.csv existant, sinon sans
      True  → forcer headers (--with-headers)
      False → forcer sans headers (--no-headers)
    """
    global IMPORT_CSV
    run_dt = datetime.now(LOCAL_TZ)
    log_path = LOGS_DIR / f"{run_dt.strftime('%Y%m%d-%H%M')}_extraction.log"
    log_entries: list[str] = []

    if not dry_run:
        IMPORT_CSV = OUTPUT_DIR / f"import_{run_dt.strftime('%Y%m%d')}.csv"

    if force_headers is None:
        write_import_headers = not has_prior_imports()
        headers_reason = "auto (aucun import existant)" if write_import_headers \
                         else "auto (imports existants détectés)"
    else:
        write_import_headers = force_headers
        headers_reason = "forcé via --with-headers" if force_headers \
                         else "forcé via --no-headers"

    def log(msg: str, level: str = "INFO"):
        prefix = {"INFO": "  ", "WARN": "⚠ ", "ERR ": "✗ ", "IGN ": "— "}
        log_entries.append(f"[{level}] {msg}")
        print(prefix.get(level, "  ") + msg)

    config     = load_config()
    patterns   = load_patterns()
    headers    = config["offres_csv_headers"]
    keywords   = config["stack_keywords"]
    blacklist  = config.get("blacklist_titres", [])
    ville_dept = {k.lower(): v for k, v in config["ville_dept"].items()}

    ledger = load_ledger(LEDGER_FILE)
    pending = sorted(
        (mid for mid, entry in ledger.items()
         if entry.get("statut_extraction", "PENDING") == "PENDING"),
        key=lambda mid: ledger[mid].get("date_email", ""),
    )

    if not pending:
        print("Aucun fichier EML en attente de traitement.")
        return

    dedup_map, max_e_id = load_dedup_map()
    ensure_offres_csv(headers, write_import_headers)

    stats = {"fichiers_ok": 0, "fichiers_partiel": 0, "erreurs": 0,
             "ignores": 0, "offres_ecrites": 0, "doublons": 0,
             "blacklistes": 0, "dry_run": dry_run}

    total = len(pending)
    headers_label = f"{'avec' if write_import_headers else 'sans'} en-tête ({headers_reason})"
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Traitement de {total} fichier(s) EML")
    if not dry_run and IMPORT_CSV:
        print(f"  → {IMPORT_CSV.name}  [{headers_label}]")
    print()

    for idx, message_id in enumerate(pending, 1):
        entry = ledger[message_id]
        rel_path = entry.get("fichier", "")
        eml_path = SOURCES_DIR / rel_path
        date_email = entry.get("date_email", "")[:10]

        pct = idx / total * 100
        print(f"[{idx}/{total} — {pct:.0f}%] {rel_path}")

        if not eml_path.exists():
            log(f"Fichier introuvable : {eml_path}", "ERR ")
            entry["statut_extraction"] = "ERREUR"
            stats["erreurs"] += 1
            continue

        try:
            msg, html, _text = get_eml_parts(eml_path)
        except Exception as e:
            log(f"Impossible de lire {rel_path} : {e}", "ERR ")
            entry["statut_extraction"] = "ERREUR"
            stats["erreurs"] += 1
            continue

        domain = sender_domain(msg)
        provider_key, provider_cfg = detect_provider(domain, patterns)

        if provider_key is None:
            log(f"Provider inconnu (domaine: {domain}) — {rel_path}", "WARN")
            entry["statut_extraction"] = "ERREUR"
            stats["erreurs"] += 1
            continue

        if provider_cfg.get("skip"):
            log(f"EML ignoré [{provider_key}] : {rel_path}", "IGN ")
            entry["statut_extraction"] = "IGNORE"
            stats["ignores"] += 1
            continue

        extractor = EXTRACTORS.get(provider_key)
        if extractor is None:
            log(f"EML ignoré [pas d'extracteur pour {provider_key}] : {rel_path}", "IGN ")
            entry["statut_extraction"] = "IGNORE"
            stats["ignores"] += 1
            continue

        try:
            raw_offers = extractor(html, msg, provider_cfg)
        except Exception as e:
            log(f"Erreur d'extraction [{provider_key}] {rel_path} : {e}", "ERR ")
            entry["statut_extraction"] = "ERREUR"
            stats["erreurs"] += 1
            continue

        if not raw_offers:
            log(f"Aucune offre extraite [{provider_key}] : {rel_path}", "WARN")
            log(f"  → Sujet : {msg.get('Subject', '?')[:80]}", "WARN")
            entry["statut_extraction"] = "PARTIEL"
            stats["fichiers_partiel"] += 1
            continue

        source_display = {
            "france_travail":   "France Travail",
            "indeed_alerte":    "Indeed",
            "indeed_match":     "Indeed",
            "linkedin":         "LinkedIn",
            "meteojob_company": "Meteojob",
            "jobijoba_alerte":  "Jobijoba",
            "talent_com":       "Talent.com",
        }.get(provider_key, provider_key)

        new_rows = []
        offer_errors = 0

        for offer in raw_offers:
            if not offer.get("titre"):
                offer_errors += 1
                log(f"  Offre ignorée (titre vide) dans {rel_path}", "WARN")
                continue

            max_e_id += 1
            eid = f"E{max_e_id:06d}"

            if not offer.get("dept") and offer.get("ville"):
                offer["dept"] = get_dept(offer["ville"], ville_dept)

            search_text = offer["titre"] + " " + offer.get("notes", "")
            stack = extract_stack(search_text, keywords)

            cle = build_cle_dedup(
                offer.get("entreprise", ""),
                offer.get("ville", ""),
                offer["titre"],
            )

            doublon_id = ""
            if cle in dedup_map:
                doublon_id = dedup_map[cle]
                stats["doublons"] += 1
                log(f"  Doublon : {cle} → {doublon_id}", "INFO")
            else:
                dedup_map[cle] = eid

            notes = offer.get("notes", "")

            bl_term = is_blacklisted(offer["titre"], blacklist)
            if bl_term:
                stats["blacklistes"] += 1
                marker = f"⛔ Blacklisté: {bl_term}"
                notes = f"{notes} | {marker}" if notes else marker

            row = {
                "ID":               eid,
                "Traite":           "FALSE",
                "Date_decouverte":  date_email,
                "Source":           source_display,
                "Titre":            offer["titre"],
                "Entreprise":       offer.get("entreprise", ""),
                "Cle_dedup":        cle,
                "Doublon_ID":       doublon_id,
                "Ville":            offer.get("ville", ""),
                "Dept":             offer.get("dept", ""),
                "Type_contrat":     offer.get("type_contrat", ""),
                "Salaire_min":      offer.get("salaire_min", ""),
                "Salaire_max":      offer.get("salaire_max", ""),
                "URL":              offer.get("url", ""),
                "URL_qualite":      offer.get("url_qualite", "vide"),
                "URL_redirect":     "",
                "Stack":            stack,
                "Raison_exclusion": f"Blacklisté: {bl_term}" if bl_term else "",
                "Date_candidature": "",
                "Notes":            notes,
                "Message_ID":       message_id,
            }
            new_rows.append(row)

        if new_rows and not dry_run:
            append_offres(new_rows, headers)

        nb_ok = len(new_rows)
        nb_err = offer_errors
        stats["offres_ecrites"] += nb_ok

        statut = "OK" if nb_err == 0 else "PARTIEL"
        entry["statut_extraction"] = statut

        if statut == "OK":
            stats["fichiers_ok"] += 1
            log(f"  {nb_ok} offre(s) {'simulées' if dry_run else 'écrites'}", "INFO")
        else:
            stats["fichiers_partiel"] += 1
            log(f"  {nb_ok} offre(s) OK, {nb_err} ignorée(s)", "WARN")

    if not dry_run:
        save_ledger(LEDGER_FILE, ledger)

    print(f"\n{'='*55}")
    print(f"{'[DRY-RUN] ' if dry_run else ''}RAPPORT DE RUN — {run_dt.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}")
    print(f"  Fichiers traités  : {stats['fichiers_ok'] + stats['fichiers_partiel']}/{total}")
    print(f"  Offres écrites    : {stats['offres_ecrites']}")
    print(f"  Doublons détectés : {stats['doublons']}")
    print(f"  Blacklistés       : {stats['blacklistes']}")
    print(f"  Fichiers ignorés  : {stats['ignores']}")
    print(f"  Fichiers partiels : {stats['fichiers_partiel']}")
    print(f"  Erreurs           : {stats['erreurs']}")
    if stats["erreurs"] or stats["fichiers_partiel"]:
        print(f"\n  ⚠  Détails dans : {log_path.name}")
    if not dry_run and IMPORT_CSV and stats["offres_ecrites"] > 0:
        print(f"\n  → À importer dans Google Sheets : {IMPORT_CSV.name}")
        print(f"     Données → Importer → Ajouter aux données actuelles")
    print(f"{'='*55}\n")

    if not dry_run:
        write_run_log(run_dt, log_entries, stats, log_path)
        append_history(run_dt, stats)
```

- [ ] **Step 4: Verify against real project data**

Run: `python3 extract_eml.py --dry-run`
Expected: completes without error. Since Task 5's migration preserved every `Statut_extraction` value, only genuinely `PENDING` emails are processed — same count as before this change.

- [ ] **Step 5: Commit**

```bash
git add extract_eml.py
git commit -m "feat: switch extract_eml.py to the unified email ledger, add Message_ID"
```

---

### Task 9: OAuth2 setup (`auth.py`)

**This task requires you (the user) to perform real actions in the Google Cloud Console and complete a real browser authorization — no agent can do this on your behalf.** Each step below is validated before moving to the next, per your request. `docs/setup_gmail_auth.md` is written incrementally as each step is actually completed, capturing what was really done (not written speculatively up front).

**Files:**
- Create: `auth.py`
- Test: `tests/test_auth.py`
- Create (incrementally, one section per step below): `docs/setup_gmail_auth.md`
- Modify: `.gitignore` (already covers `token.json`/`credentials.json` from Task 1 — verify, don't re-add)

**Interfaces:**
- Produces: `get_credentials() -> Credentials`, `SCOPES`, `TOKEN_FILE`, `CREDENTIALS_FILE`. Consumed by Task 10 (`fetch_gmail.py`).

- [ ] **Step 1 (manual): Create the Google Cloud project and enable the Gmail API**

In the Google Cloud Console: create a new project (or pick an existing personal one), then enable the "Gmail API" for it (APIs & Services → Library → search "Gmail API" → Enable).

**Validation:** APIs & Services → Enabled APIs shows "Gmail API" listed. Write one paragraph in `docs/setup_gmail_auth.md` documenting the project name/ID used (no secrets).

- [ ] **Step 2 (manual): Create OAuth2 credentials**

APIs & Services → Credentials → Create Credentials → OAuth client ID → Application type "Desktop app". Download the resulting JSON, save it as `credentials.json` at the project root.

**Validation:** `credentials.json` exists at the project root and `cat credentials.json | python3 -m json.tool` parses without error. Confirm it is **not** tracked by git: `git check-ignore credentials.json` prints the filename (confirms it's ignored).

- [ ] **Step 3: Write the failing tests for `auth.py`**

```python
# tests/test_auth.py
from unittest.mock import MagicMock, patch

import auth


def test_get_credentials_returns_valid_cached_token(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token.json")
    (tmp_path / "token.json").write_text("{}", encoding="utf-8")

    fake_creds = MagicMock(valid=True)
    with patch.object(auth.Credentials, "from_authorized_user_file", return_value=fake_creds):
        result = auth.get_credentials()

    assert result is fake_creds


def test_get_credentials_refreshes_expired_token(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token.json")
    (tmp_path / "token.json").write_text("{}", encoding="utf-8")

    fake_creds = MagicMock(valid=False, expired=True, refresh_token="r")
    fake_creds.to_json.return_value = '{"refreshed": true}'
    with patch.object(auth.Credentials, "from_authorized_user_file", return_value=fake_creds):
        result = auth.get_credentials()

    fake_creds.refresh.assert_called_once()
    assert result is fake_creds
    assert (tmp_path / "token.json").read_text(encoding="utf-8") == '{"refreshed": true}'


def test_get_credentials_runs_flow_when_no_token_file(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token.json")
    monkeypatch.setattr(auth, "CREDENTIALS_FILE", tmp_path / "credentials.json")

    fake_creds = MagicMock()
    fake_creds.to_json.return_value = '{"new": true}'
    fake_flow = MagicMock()
    fake_flow.run_local_server.return_value = fake_creds

    with patch.object(auth.InstalledAppFlow, "from_client_secrets_file", return_value=fake_flow):
        result = auth.get_credentials()

    fake_flow.run_local_server.assert_called_once_with(port=0)
    assert result is fake_creds
    assert (tmp_path / "token.json").read_text(encoding="utf-8") == '{"new": true}'
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'auth'`

- [ ] **Step 5: Write `auth.py`**

```python
"""OAuth2 credential management for the Gmail API.

token.json and credentials.json are never committed (see .gitignore).
"""

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

ROOT = Path(__file__).parent
CREDENTIALS_FILE = ROOT / "credentials.json"
TOKEN_FILE = ROOT / "token.json"


def get_credentials() -> Credentials:
    """Return valid Gmail API credentials, refreshing or running the
    interactive OAuth2 flow as needed. Writes/updates token.json."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
        creds = flow.run_local_server(port=0)

    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: 3 passed

- [ ] **Step 7 (manual): First real authorization flow**

Run: `python3 -c "from auth import get_credentials; get_credentials(); print('OK')"`
This opens a browser window — log in with the Gmail account to monitor, grant the read-only permission.

**Validation:** the command prints `OK`, and `token.json` now exists at the project root. Run `git check-ignore token.json` to confirm it's ignored.

- [ ] **Step 8 (manual): Verify the token is actually usable**

Run:
```bash
python3 -c "
from auth import get_credentials
from googleapiclient.discovery import build
service = build('gmail', 'v1', credentials=get_credentials())
profile = service.users().getProfile(userId='me').execute()
print(profile['emailAddress'])
"
```
Expected: prints the monitored Gmail address — confirms the token is valid and scoped correctly.

- [ ] **Step 9 (manual): Verify refresh works**

Note the `expiry` field inside `token.json` (`cat token.json`). Re-run the Step 8 command after the token would have expired (or manually edit `token.json`'s `expiry` to a past date, then re-run) — `get_credentials()` should refresh silently rather than reopening a browser.

**Validation:** command succeeds without a browser popping up; `token.json`'s `expiry` timestamp has moved forward.

- [ ] **Step 10: Finalize `docs/setup_gmail_auth.md` and commit**

Consolidate the notes from Steps 1–2 (project setup) and the commands from Steps 7–9 (first-run + refresh verification) into `docs/setup_gmail_auth.md`, written as a walkthrough for future-you re-doing this on a new machine.

```bash
git add auth.py tests/test_auth.py docs/setup_gmail_auth.md
git commit -m "feat: add Gmail OAuth2 credential management"
```

---

### Task 10: `fetch_gmail.py`

**Files:**
- Create: `fetch_gmail.py`
- Test: `tests/test_fetch_gmail.py`

**Interfaces:**
- Consumes: `providers.load_domain_map`, `providers.sender_domain`, `providers.expected_folder` (Task 2), `ledger.load_ledger`, `ledger.save_ledger` (Task 4), `auth.get_credentials` (Task 9).
- Produces: `run(dry_run: bool, since_days: int | None = None) -> None`. Consumed by Task 11 (`run_pipeline.py`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fetch_gmail.py
import re
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from fetch_gmail import (
    build_filename,
    build_query,
    collect_sender_domains,
    compute_after_date,
    determine_after_date,
    list_message_ids,
    slugify_subject,
)


def test_collect_sender_domains_excludes_skip_entries_and_dedupes():
    patterns = {
        "_comment": "ignored",
        "indeed_alerte": {"sender_domains": ["jobalert.indeed.com", "indeed.com"]},
        "indeed_match": {"sender_domains": ["match.indeed.com"]},
        "meteojob_company": {"sender_domains": ["meteojob.com"]},
        "meteojob_digest": {"sender_domains": ["meteojob.com"], "skip": True},
    }
    assert collect_sender_domains(patterns) == [
        "indeed.com", "jobalert.indeed.com", "match.indeed.com", "meteojob.com",
    ]


def test_build_query_combines_senders_and_date():
    query = build_query(["indeed.com", "linkedin.com"], "2026/08/05")
    assert query == "({from:indeed.com from:linkedin.com}) after:2026/08/05"


def test_build_query_raises_on_empty_senders():
    with pytest.raises(ValueError):
        build_query([], "2026/08/05")


def test_compute_after_date_applies_overlap_margin():
    last_fetch = datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc)
    assert compute_after_date(last_fetch) == "2026/08/06"


def test_compute_after_date_rolls_back_a_day_across_midnight():
    last_fetch = datetime(2026, 8, 6, 2, 0, tzinfo=timezone.utc)
    assert compute_after_date(last_fetch) == "2026/08/05"


def test_determine_after_date_uses_last_fetch_from_ledger():
    ledger = {
        "<msg-1>": {"gmail_id": "abc", "fetched_at": "2026-08-01T10:00:00Z"},
        "<msg-2>": {"gmail_id": "def", "fetched_at": "2026-08-05T09:00:00Z"},
        "<msg-3>": {"gmail_id": "before_gmail_api", "fetched_at": "2020-01-01T00:00:00Z"},
    }
    assert determine_after_date(ledger, since_days=None) == "2026/08/05"


def test_determine_after_date_falls_back_to_since_days_when_ledger_empty():
    result = determine_after_date({}, since_days=30)
    assert re.match(r"^\d{4}/\d{2}/\d{2}$", result)


def test_determine_after_date_raises_without_history_or_since_days():
    with pytest.raises(ValueError):
        determine_after_date({}, since_days=None)


def test_build_filename_includes_gmail_id_and_slug():
    assert build_filename("18d4a2f", "3 nouvelles offres !") == "18d4a2f-3-nouvelles-offres.eml"


def test_build_filename_is_unique_for_identical_subjects_via_gmail_id():
    a = build_filename("id-1", "Alerte emploi")
    b = build_filename("id-2", "Alerte emploi")
    assert a != b


def test_slugify_subject_handles_accents_and_empty():
    assert slugify_subject("Café à Paris") == "caf-paris"
    assert slugify_subject("") == "sans-sujet"


def test_list_message_ids_single_page():
    service = MagicMock()
    messages_resource = service.users.return_value.messages.return_value
    first_request = MagicMock()
    first_request.execute.return_value = {"messages": [{"id": "a"}, {"id": "b"}]}
    messages_resource.list.return_value = first_request
    messages_resource.list_next.return_value = None

    assert list_message_ids(service, "some query") == ["a", "b"]


def test_list_message_ids_paginates_across_multiple_pages():
    service = MagicMock()
    messages_resource = service.users.return_value.messages.return_value

    first_request = MagicMock()
    first_request.execute.return_value = {"messages": [{"id": "a"}], "nextPageToken": "tok"}
    second_request = MagicMock()
    second_request.execute.return_value = {"messages": [{"id": "b"}]}

    messages_resource.list.return_value = first_request
    messages_resource.list_next.side_effect = [second_request, None]

    result = list_message_ids(service, "some query")

    assert result == ["a", "b"]
    assert messages_resource.list_next.call_count == 2


def test_list_message_ids_no_results():
    service = MagicMock()
    messages_resource = service.users.return_value.messages.return_value
    request = MagicMock()
    request.execute.return_value = {}
    messages_resource.list.return_value = request
    messages_resource.list_next.return_value = None

    assert list_message_ids(service, "some query") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fetch_gmail.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fetch_gmail'`

- [ ] **Step 3: Write `fetch_gmail.py`**

```python
#!/usr/bin/env python3
"""Fetches new .eml alert emails from Gmail via the API, routes them into
sources/<provider>/, and records them in logs/email_ledger.json.

Usage:
    python3 fetch_gmail.py [--dry-run] [--since-days N]

--since-days is only needed for the very first run (no prior fetch history
in the ledger). Every subsequent run derives its start date automatically
from the most recent fetched_at in the ledger.
"""

import argparse
import base64
import email
import json
import re
from datetime import datetime, timedelta, timezone
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path

from googleapiclient.discovery import build

import auth
from ledger import load_ledger, save_ledger
from providers import expected_folder, load_domain_map, sender_domain

ROOT = Path(__file__).parent
SOURCES_DIR = ROOT / "sources"
LOGS_DIR = ROOT / "logs"
CONFIG_DIR = ROOT / "config"
PATTERNS_FILE = CONFIG_DIR / "scraping_patterns.json"
LEDGER_FILE = LOGS_DIR / "email_ledger.json"

OVERLAP_MARGIN = timedelta(hours=6)
IGNORED_GMAIL_IDS = {"before_gmail_api", "manual"}


def load_patterns() -> dict:
    with PATTERNS_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def collect_sender_domains(patterns: dict) -> list[str]:
    """Flatten sender_domains from every non-skip provider entry in
    scraping_patterns.json, deduplicated and sorted for stable query
    output. Digest-only entries (skip: true) are excluded, though in
    practice their domains are already covered by a sibling alert
    provider on the same domain."""
    domains = set()
    for key, p in patterns.items():
        if key.startswith("_") or p.get("skip"):
            continue
        domains.update(p.get("sender_domains", []))
    return sorted(domains)


def build_query(sender_domains: list[str], after_date: str) -> str:
    """Build a Gmail search query combining sender domains (OR'd via {})
    and an after: date filter."""
    if not sender_domains:
        raise ValueError("Aucun domaine expéditeur configuré (scraping_patterns.json)")
    senders = " ".join(f"from:{d}" for d in sender_domains)
    return f"({{{senders}}}) after:{after_date}"


def compute_after_date(last_fetch: datetime) -> str:
    """Gmail's after: filter is day-granularity; subtract a safety margin
    so a fetch late in the day still gets covered when re-run early the
    next day, without needing second-level precision."""
    return (last_fetch - OVERLAP_MARGIN).strftime("%Y/%m/%d")


def compute_last_fetch(ledger: dict) -> datetime | None:
    """Most recent fetched_at among real (API-sourced) ledger entries, or
    None if nothing has ever been fetched via the API yet."""
    timestamps = [
        e["fetched_at"] for e in ledger.values()
        if e.get("gmail_id") not in IGNORED_GMAIL_IDS and e.get("fetched_at")
    ]
    if not timestamps:
        return None
    latest = max(timestamps)
    return datetime.strptime(latest, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def determine_after_date(ledger: dict, since_days: int | None) -> str:
    last_fetch = compute_last_fetch(ledger)
    if last_fetch is not None:
        return compute_after_date(last_fetch)
    if since_days is not None:
        start = datetime.now(timezone.utc) - timedelta(days=since_days)
        return start.strftime("%Y/%m/%d")
    raise ValueError(
        "Aucun fetch précédent dans le ledger et --since-days non fourni : "
        "impossible de déterminer un point de départ."
    )


def slugify_subject(subject: str, max_len: int = 40) -> str:
    """Turn an email subject into a filesystem-safe slug."""
    ascii_subject = subject.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_subject).strip("-").lower()
    return slug[:max_len] or "sans-sujet"


def build_filename(gmail_id: str, subject: str) -> str:
    """gmail_id guarantees uniqueness by construction — no collision
    detection needed even when two alerts share a near-identical subject."""
    return f"{gmail_id}-{slugify_subject(subject)}.eml"


def list_message_ids(service, query: str) -> list[str]:
    """Return all Gmail message IDs matching the query, paginating via
    nextPageToken (normal volume never needs a second page, but this
    avoids silently dropping messages after a long gap between runs)."""
    ids = []
    request = service.users().messages().list(userId="me", q=query)
    while request is not None:
        response = request.execute()
        ids.extend(m["id"] for m in response.get("messages", []))
        request = service.users().messages().list_next(request, response)
    return ids


def download_raw_eml(service, gmail_id: str) -> bytes:
    raw = service.users().messages().get(
        userId="me", id=gmail_id, format="raw"
    ).execute()["raw"]
    return base64.urlsafe_b64decode(raw)


def run(dry_run: bool, since_days: int | None = None) -> None:
    patterns = load_patterns()
    domain_map = load_domain_map(PATTERNS_FILE)
    sender_domains = collect_sender_domains(patterns)

    ledger = load_ledger(LEDGER_FILE)
    after_date = determine_after_date(ledger, since_days)
    query = build_query(sender_domains, after_date)

    print(f"{'[DRY-RUN] ' if dry_run else ''}Requête Gmail : {query}")

    service = build("gmail", "v1", credentials=auth.get_credentials())
    gmail_ids = list_message_ids(service, query)
    known_gmail_ids = {e.get("gmail_id") for e in ledger.values()}
    new_ids = [gid for gid in gmail_ids if gid not in known_gmail_ids]

    print(f"{len(gmail_ids)} message(s) trouvé(s), {len(new_ids)} nouveau(x)")

    downloaded = 0
    for gmail_id in new_ids:
        raw = download_raw_eml(service, gmail_id)
        msg = email.message_from_bytes(raw, policy=policy.default)
        message_id = (msg.get("Message-ID") or "").strip() or None

        if message_id is None:
            print(f"  SKIP (Message-ID introuvable) : {gmail_id}")
            continue
        if message_id in ledger:
            print(f"  SKIP (déjà connu sous un autre gmail_id) : {gmail_id}")
            continue

        domain = sender_domain(msg.get("From", ""))
        folder = expected_folder(domain, domain_map)
        if folder is None:
            print(f"  SKIP (domaine inconnu: {domain}) : {gmail_id}")
            continue

        filename = build_filename(gmail_id, msg.get("Subject", ""))
        dest_dir = SOURCES_DIR / folder
        dest_path = dest_dir / filename

        raw_date = msg.get("Date", "")
        dt = parsedate_to_datetime(raw_date) if raw_date else None
        date_email = dt.strftime("%Y-%m-%dT%H:%M:%S%z") if dt else ""

        print(f"  GET  {filename} → {folder}/")
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(raw)
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            ledger[message_id] = {
                "gmail_id": gmail_id,
                "fichier": str(dest_path.relative_to(SOURCES_DIR)),
                "date_email": date_email,
                "fetched_at": now_str,
                "indexed_at": "",
                "statut_extraction": "PENDING",
            }
        downloaded += 1

    if not dry_run:
        save_ledger(LEDGER_FILE, ledger)

    print(f"\n{'Simulation' if dry_run else 'Résultat'} : {downloaded} email(s) téléchargé(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--since-days", type=int, default=None,
                        help="Point de départ pour le tout premier fetch (aucun historique en ledger)")
    args = parser.parse_args()
    run(dry_run=args.dry_run, since_days=args.since_days)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fetch_gmail.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add fetch_gmail.py tests/test_fetch_gmail.py
git commit -m "feat: add fetch_gmail.py for automated .eml retrieval"
```

- [ ] **Step 6 (manual): First real run**

Run: `python3 fetch_gmail.py --dry-run --since-days 3`
Expected: prints the constructed query and how many messages it found/would download, with no errors. Review the query string for sanity (correct domains, plausible date) before ever running without `--dry-run`.

---

### Task 11: `run_pipeline.py`

**Files:**
- Create: `run_pipeline.py`
- Test: `tests/test_run_pipeline.py`

**Interfaces:**
- Consumes: `fetch_gmail.run(dry_run)` (Task 10), `rename_eml.run(dry_run, purge)` (Task 7), `extract_eml.main(dry_run, force_headers=None)` (Task 8).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_run_pipeline.py
import pytest

import run_pipeline


def test_run_pipeline_calls_steps_in_order(monkeypatch):
    calls = []
    monkeypatch.setattr(run_pipeline.fetch_gmail, "run",
                        lambda dry_run: calls.append(("fetch", dry_run)))
    monkeypatch.setattr(run_pipeline.rename_eml, "run",
                        lambda dry_run, purge: calls.append(("rename", dry_run, purge)))
    monkeypatch.setattr(run_pipeline.extract_eml, "main",
                        lambda dry_run: calls.append(("extract", dry_run)))

    run_pipeline.run_pipeline(dry_run=True)

    assert calls == [("fetch", True), ("rename", True, False), ("extract", True)]


def test_run_pipeline_stops_on_fetch_failure(monkeypatch):
    def failing_fetch(dry_run):
        raise RuntimeError("network error")

    calls = []
    monkeypatch.setattr(run_pipeline.fetch_gmail, "run", failing_fetch)
    monkeypatch.setattr(run_pipeline.rename_eml, "run",
                        lambda dry_run, purge: calls.append("rename"))
    monkeypatch.setattr(run_pipeline.extract_eml, "main",
                        lambda dry_run: calls.append("extract"))

    with pytest.raises(RuntimeError):
        run_pipeline.run_pipeline(dry_run=False)

    assert calls == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_run_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'run_pipeline'`

- [ ] **Step 3: Write `run_pipeline.py`**

```python
#!/usr/bin/env python3
"""Runs the full pipeline: fetch_gmail -> rename_eml -> extract_eml.

Usage:
    python3 run_pipeline.py [--dry-run]

Fail-fast: stops at the first step that raises. Later steps never run
against a state left inconsistent by an earlier failure.
"""

import argparse

import extract_eml
import fetch_gmail
import rename_eml


def run_pipeline(dry_run: bool) -> None:
    print("=== 1/3 — Fetch Gmail ===")
    fetch_gmail.run(dry_run=dry_run)

    print("\n=== 2/3 — Rename & index ===")
    rename_eml.run(dry_run=dry_run, purge=False)

    print("\n=== 3/3 — Extract offers ===")
    extract_eml.main(dry_run=dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_pipeline(dry_run=args.dry_run)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_run_pipeline.py -v`
Expected: 2 passed

- [ ] **Step 5: Full dry-run against real project data**

Run: `python3 run_pipeline.py --dry-run`
Expected: all three steps run in sequence, aggregated output visible, no exceptions.

- [ ] **Step 6: Commit**

```bash
git add run_pipeline.py tests/test_run_pipeline.py
git commit -m "feat: add run_pipeline.py orchestrator"
```

---

### Task 12: Documentation

**Files:**
- Modify: `README.md` (translate to English, update for the new pipeline)
- Create: `README.fr.md` (French, mirrors `README.md`)

**Interfaces:**
- None (docs only).

- [ ] **Step 1: Write `README.md`**

Translate the current French `README.md` to English, then update it to reflect the new pipeline:
- Update the pipeline diagram at the top:
  ```
  fetch_gmail.py       ← Gmail API fetch, OAuth2, routes into sources/<provider>/
          ↓
  sources/<provider>/  ← .eml files per platform
          ↓
    rename_eml.py       ← renaming, Message-ID dedup, ledger indexing
          ↓
    extract_eml.py       ← offer extraction → CSV
          ↓
  output/import_YYYYMMDD.csv  ← manual import into Google Sheets

  run_pipeline.py runs all three steps in sequence (recommended entry point).
  ```
- Add a `fetch_gmail.py` section (usage, `--dry-run`, `--since-days`), matching the style of the existing `rename_eml.py`/`extract_eml.py` sections.
- Add a `run_pipeline.py` section as the recommended entry point.
- Replace the `eml_index.csv` description with the `email_ledger.json` format (one JSON object keyed by `message_id`, fields `gmail_id`/`fichier`/`date_email`/`fetched_at`/`indexed_at`/`statut_extraction`; `gmail_id` is `"before_gmail_api"` for pre-migration entries, `"manual"` for files indexed without ever being fetched via the API).
- Add a "Testing" section:
  ```markdown
  ## Testing

  ```bash
  pip install -r requirements-dev.txt
  pytest
  ruff check .
  ruff format --check .
  pre-commit install   # once, to enable the git hook
  ```
  ```
- Add a one-line pointer: `See docs/setup_gmail_auth.md for the Gmail OAuth2 setup walkthrough.`
- Add the `Message_ID` column to the "Colonnes de référence" → "Reference columns" table (column U).
- Add a "Roadmap" section documenting the Sheets-API-automation option as a deliberately deferred idea (per the design doc's Roadmap section).

- [ ] **Step 2: Write `README.fr.md`**

Same structure and content as `README.md`, in French — this is the original README's content, updated with the same pipeline/section changes described in Step 1.

- [ ] **Step 3: Commit**

```bash
git add README.md README.fr.md
git commit -m "docs: update README for the Gmail fetch pipeline, add French translation"
```

---

## Execution Notes

- Tasks 1–8 are fully automatable (TDD cycles, no external dependencies).
- Task 9 requires the user's direct participation (Google Cloud Console, browser OAuth consent) — do not attempt to script around this.
- Task 10 depends on Task 9 being complete (`auth.get_credentials()` must work against a real account before `fetch_gmail.py`'s Step 6 manual verification can run, though its unit tests in Step 1–4 don't need real credentials).
- Tasks 5 and 6 (migrations) should run once, against real project data, after their respective code is merged — not in CI/test mode.
