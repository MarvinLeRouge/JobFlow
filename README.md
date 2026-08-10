# Job Search Tracker

Python pipeline for processing job alert emails.
Offers are fetched from Gmail, extracted from `.eml` files, deduplicated, and synced into Google Sheets.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design rationale behind the pipeline, the dedup strategy, and the provider parsers.

---

## Overview

```
fetch_gmail.py        ← Gmail API fetch, OAuth2, routes into sources/<provider>/
        ↓
sources/<provider>/   ← .eml files per platform
        ↓
  rename_eml.py       ← renaming, Message-ID dedup, ledger indexing
        ↓
  extract_eml.py      ← offer extraction → CSV
        ↓
output/import_YYYYMMDD.csv  ← new offers from this run, still produced
        ↓
  sheets_sync.py      ← appends new rows to the Sheet, reproduces formatting
        ↓
  Google Sheet         ← master tracking sheet
```

`run_pipeline.py` runs all four steps in sequence and is the recommended entry point.

---

## Migration (one-time, after upgrading)

Two one-shot scripts bring an existing installation up to date with the Gmail pipeline. They must be run **in this order**, and both must be run **before** `extract_eml.py` or `run_pipeline.py` is used for real: otherwise `Message_ID` is silently dropped from the exported rows.

**1. Legacy index to ledger** (turns `logs/eml_index.csv` into `logs/email_ledger.json`):

```bash
python3 migrate_eml_index_to_ledger.py --dry-run   # review the entry count first
python3 migrate_eml_index_to_ledger.py             # write logs/email_ledger.json
```

The old `logs/eml_index.csv` is left in place, remove it by hand once the ledger looks right.

**2. Message_ID column** (adds the column to `output/offres.csv` and to `offres_csv_headers` in `config/config.json`):

```bash
cp output/offres.csv output/offres.csv.bak         # recommended, see the note below
python3 migrate_offres_add_message_id.py --dry-run # review the row count first
python3 migrate_offres_add_message_id.py           # write the column
```

Both files are written to a temp file and moved into place, so an interrupted run cannot truncate them, and `config/config.json` is edited in place rather than reserialized, so its formatting survives. Backing up `output/offres.csv` by hand is still recommended: `output/` is git-ignored, there is no history to fall back on.

Once both migrations have run for real, `extract_eml.py` and `run_pipeline.py` can be used normally. The very first fetch after migration needs an explicit start date, since migrated entries carry no real fetch history:

```bash
python3 run_pipeline.py --since-days 30
```

**Sheets sync target:** `sheets_sync.py` itself needs no data migration, but the real spreadsheet ID must be set in `config/config.local.json` (git-ignored, see [Configuration](#configuration) below) before relying on `sheets_sync.py` or `run_pipeline.py` for actual use.

---

## Scripts

### `fetch_gmail.py`

Queries the Gmail API for new alert emails, routes them into `sources/<provider>/`, and records each one in `logs/email_ledger.json`.

```bash
python3 fetch_gmail.py                  # fetch new emails
python3 fetch_gmail.py --dry-run        # simulation, no download or write
python3 fetch_gmail.py --since-days 30  # first run only: emails from the last 30 days
```

`--since-days` is only needed on the very first run, when the ledger has no fetch history yet. Every later run derives its start date automatically from the most recent `fetched_at` in the ledger, with a safety margin so nothing falls through the gap between two runs.

Requires a one-time Gmail OAuth2 setup, see `docs/setup_gmail_auth.md`.

Files written: `.eml` files under `sources/<provider>/`, `logs/email_ledger.json`.

---

### `rename_eml.py`

Renames `.eml` files to the `yyyymmdd-hhmm-name.eml` format, detects duplicates by Message-ID, and checks that each file sits in the right provider folder.

```bash
python3 rename_eml.py              # rename + dedup
python3 rename_eml.py --dry-run    # simulation, no changes
python3 rename_eml.py --check      # check folders only, read-only
python3 rename_eml.py --purge      # empty sources/_duplicates/
```

Files written: `logs/email_ledger.json`.

---

### `extract_eml.py`

Extracts offers from every `.eml` marked `PENDING` in the ledger, deduplicates them, detects the tech stack and blacklisted titles, then writes two CSV files. `extract_eml.py` itself is a thin orchestrator; the actual parsing/filtering/IO logic lives in the `extract/` package (`extract/providers/` for the per-provider HTML parsers, `extract/filters.py` for dedup/blacklist/stack, `extract/geo.py` for city→département resolution, `extract/io.py` for CSV/log writing).

```bash
python3 extract_eml.py                # full extraction
python3 extract_eml.py --dry-run      # simulation, no write
python3 extract_eml.py --with-headers # force the header row in the import CSV
python3 extract_eml.py --no-headers   # force no header row
```

Files written:
- `output/offres.csv` - cumulative local archive (dedup reference, **do not reimport into Sheets**)
- `output/import_YYYYMMDD.csv` - new rows from this run only, to import into Sheets
- `logs/email_ledger.json`, `logs/extraction_history.csv`, `logs/YYYYMMDD-HHMM_extraction.log`

Supported providers: France Travail, Indeed (alerts + direct match), LinkedIn, Meteojob, Jobijoba, Talent.com.

---

### `sheets_sync.py`

Syncs new offers from the latest `output/import_YYYYMMDD.csv` into the real Google Sheet: compares the sheet's own highest offer ID (column A) against the CSV to find only the rows it doesn't already have, appends them, reproduces column B's (`Traite`) formula/dropdown and column R's (`Raison_exclusion`) dropdown on those rows by copying formatting from the dedicated "Références" tab, and extends the sheet's row-level conditional formatting rules (duplicate/blacklist/alternance highlighting, "En cours" status in column A) to cover the newly appended rows.

```bash
python3 sheets_sync.py             # sync new rows to the Sheet
python3 sheets_sync.py --dry-run   # simulation, no write, just reports what would sync
python3 sheets_sync.py --ack-error # acknowledge and clear a blocked error state
```

It only looks at **today's** `output/import_YYYYMMDD.csv`. If `extract_eml.py` hasn't produced one today, it prints a message and exits without error.

**Error gate:** on any failure, the error message and timestamp are recorded to `logs/sheets_sync_error.json`. Every later run of `sheets_sync.py` or `run_pipeline.py` then stops immediately with that message until it is acknowledged with `python3 sheets_sync.py --ack-error`. `fetch_gmail.py`, `rename_eml.py` and `extract_eml.py` are unaffected by the gate and remain usable individually.

Files written: nothing durable locally besides `logs/sheets_sync_error.json` on failure; the sheet itself is the only lasting output.

---

### `run_pipeline.py`

Recommended entry point. Runs `fetch_gmail` → `rename_eml` → `extract_eml` → `sheets_sync` in sequence.

```bash
python3 run_pipeline.py                  # full pipeline
python3 run_pipeline.py --dry-run        # simulate all four steps
python3 run_pipeline.py --since-days 30  # first run after migration
```

`--since-days` is forwarded to `fetch_gmail.py`. It is needed for the very first run after the [migration](#migration-one-time-after-upgrading), because migrated ledger entries do not count as fetch history: without it, the run stops on "impossible de déterminer un point de départ".

Fail-fast: the pipeline stops at the first step that raises, so a later step never runs against a state left inconsistent by an earlier failure. It also stops before step 1 if `sheets_sync.py` has an unacknowledged error left over from a previous run (see the error gate above).

---

### `inspect_sheet_formatting.py`

One-off diagnostic tool built during `sheets_sync.py`'s feasibility spike, not part of the regular pipeline. Prints a sheet's cell formulas, data validation rules, and conditional formatting, read directly via the Sheets API, to inspect exactly what needs to be replicated.

```bash
python3 inspect_sheet_formatting.py <spreadsheet_id> <sheet_name>
```

Run only against a duplicated **test** sheet, never production. Files written: none, prints to stdout.

---

## Gmail OAuth2 setup

`fetch_gmail.py` needs a Google Cloud project with the Gmail API enabled and a one-time OAuth2 authorization (`credentials.json` and `token.json`, both git-ignored). See `docs/setup_gmail_auth.md` for the full walkthrough, including the "Access blocked" testing-mode pitfall and how to verify a silent token refresh.

---

## Google Sheets OAuth2 setup

`sheets_sync.py` needs its own OAuth2 token, `token_sheets.json` (git-ignored), authorized with the `spreadsheets` scope. It reuses the same OAuth client as Gmail (`credentials.json`) but keeps a separate token file since the scopes differ. The first real run opens a browser for a one-time consent screen; after that, `auth.get_credentials()` refreshes the token silently, the same way it already does for Gmail.

---

## Configuration

### `config/config.json`

| Key | Role |
|-----|------|
| `offres_csv_headers` | order of CSV columns |
| `stack_keywords` | keywords used to detect the tech stack |
| `ville_dept` | city → département number mapping |
| `blacklist_titres` | titles to auto-flag (e.g. "nounou", "garde d'enfant") |
| `sheets_sync` | Google Sheets sync target and reference-cell coordinates, see below |

#### `sheets_sync`

| Key | Role |
|-----|------|
| `spreadsheet_id` | ID of the target Google Sheet (from its URL) - see note below |
| `sheet_name` | tab name holding the offers (e.g. `Offres`) |
| `reference_sheet_name` | tab holding the reference cells `sheets_sync.py` copies formatting from (e.g. `Références`) |
| `reference_row_b` | row number in the reference tab holding column B's (`Traite`) formula/dropdown to copy |
| `reference_row_r` | row number in the reference tab holding column R's (`Raison_exclusion`) dropdown to copy |

> `spreadsheet_id` is **not** set in `config/config.json` (left as an empty placeholder there, so it stays safe to commit). The real ID lives in `config/config.local.json` (git-ignored, merged over `config.json` by `sheets_sync.load_config()`), so it never ends up in git history. Copy `config/config.local.json.example` to `config/config.local.json` and fill in the real spreadsheet ID to get started.

#### Important: the Références tab is a live dependency

The `reference_sheet_name` tab is not a one-time setup aid: `sheets_sync.py` reads `reference_row_b` and `reference_row_r` on **every sync run**, not just once, and copies their formatting onto each newly-appended row. This is because dropdown/validation colors turned out not to be readable via the Sheets API at all, so live copy-paste from these two reference cells is the only way to reproduce them.

Nothing enforces this tab's structure. Reordering rows in it (e.g. inserting a row above row 2), or clearing/changing the formatting or dropdown validation on the reference cells themselves, makes every future sync silently copy wrong or missing formatting onto new rows - with no error and no error-gate trip. The error gate only catches the tab being renamed or deleted outright, not its internal rows changing.

### `config/scraping_patterns.json`

Extraction patterns per provider: sender domain, source folder, regular expressions.

---

## The ledger (`logs/email_ledger.json`)

Shared tracking file used by `fetch_gmail.py`, `rename_eml.py` and `extract_eml.py`, replacing the older `logs/eml_index.csv`. It is a single JSON object keyed by Message-ID, one entry per email:

```json
{
  "<msg-1@example.com>": {
    "gmail_id": "18f2a9c7b3e4d501",
    "fichier": "indeed/20260806-1032-foo.eml",
    "date_email": "2026-08-06T10:32:00+0200",
    "fetched_at": "2026-08-06T10:35:12Z",
    "indexed_at": "2026-08-06T10:35:12Z",
    "statut_extraction": "PENDING"
  }
}
```

- `gmail_id`: the Gmail API message ID. `"before_gmail_api"` for entries migrated from the legacy `eml_index.csv`, `"manual"` for files indexed by `rename_eml.py` that were never fetched through the API (dropped into `sources/` by hand).
- `fichier`: file path relative to `sources/`.
- `date_email`: the email's `Date` header, parsed to an ISO 8601 timestamp with offset.
- `fetched_at`: UTC timestamp of the `fetch_gmail.py` download. For entries migrated from the legacy `eml_index.csv`, it is set to the same value as `indexed_at` (the old `Date_indexation` column), not left empty.
- `indexed_at`: UTC timestamp of the last `rename_eml.py` pass over this file.
- `statut_extraction`: `PENDING`, `OK`, `PARTIEL`, `ERREUR` or `IGNORE`, set by `extract_eml.py` once it has processed the file.

---

## Deduplication

The dedup key (`Cle_dedup`) is built from:
- the normalized company name (lowercase, no accents or hyphens)
- the normalized city
- a slug of the title (no stop words or H/F mentions, truncated to 25 characters)

Format: `entreprise|ville|titreslugtronque`

If an offer with the same key already exists in `offres.csv`, the `Doublon_ID` column is filled with the ID of the first occurrence.

---

## Title blacklist

Terms defined in `blacklist_titres` (config.json) are searched for in the title on every extraction, case- and accent-insensitive.

When a title matches:
- `Raison_exclusion`: `Blacklisté: <term>`
- `Notes`: `⛔ Blacklisté: <term>`

The row is kept in the CSV and imported normally into Sheets.

---

## Google Sheets - import and formatting

**Import:** now automated by `sheets_sync.py` (see above). Manual import (Data → Import → Append to current sheet, selecting `output/import_YYYYMMDD.csv`) is no longer the normal path, but still works as a fallback if `sheets_sync.py` is blocked or unavailable.

**Conditional formatting** (set up once on the sheet, range `A2:U`):

| Priority | Color | Formula | Meaning |
|----------|-------|---------|---------|
| 1 (high) | Yellow | `=$H2<>""` | Duplicate |
| 2 | Red | `=ISNUMBER(SEARCH("Blacklist";$T2))` | Blacklisted |

> Reference columns: A=ID, B=Traite, C=Date_decouverte, D=Source, E=Titre, F=Entreprise, G=Cle_dedup, H=Doublon_ID, I=Ville, J=Dept, K=Type_contrat, L=Salaire_min, M=Salaire_max, N=URL, O=URL_qualite, P=URL_redirect, Q=Stack, R=Raison_exclusion, S=Date_candidature, T=Notes, U=Message_ID
>
> Columns A through T are unchanged from before this pipeline's Gmail integration. `Message_ID` was appended as the last column (U) rather than inserted, so the conditional formatting formulas above (and any other formula referencing a lettered column) keep working without adjustment.
>
> The sheet also carries two further row-level rules not detailed here (alternance/stage highlighting and the "En cours" status highlight, the latter scoped to column A only). `sheets_sync.py` extends all four rules' row ranges automatically when it appends new rows, whichever column scope each one already has.

---

## Testing

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
ruff format --check .
pre-commit install   # once, to enable the git hook
```

---

## Adding a provider

1. Create `sources/<provider>/`
2. Add an entry in `config/scraping_patterns.json`
3. Implement `extract_<provider>(html, msg, patterns)` in a new `extract/providers/<provider>.py`
4. Import it and add it to the `EXTRACTORS` table in `extract/providers/__init__.py`
5. Add tests in `tests/extract/providers/test_<provider>.py`
6. Test: `python3 extract_eml.py --dry-run`

---

## Roadmap

**Automating the Sheets import** was implemented in `sheets_sync.py` (see above). Offers now land directly in the master tracking sheet via the Google Sheets API, gated behind a persistent error state that blocks further syncs after a failed run until acknowledged, closing the gap this section used to describe as deliberately deferred.

---

## License

[MIT](LICENSE)
