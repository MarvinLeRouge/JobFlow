# Job Search Tracker

Python pipeline for processing job alert emails.
Offers are fetched from Gmail, extracted from `.eml` files, deduplicated, and exported to CSV for import into Google Sheets.

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
output/import_YYYYMMDD.csv  ← manual import into Google Sheets
```

`run_pipeline.py` runs all three steps in sequence and is the recommended entry point.

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

Extracts offers from every `.eml` marked `PENDING` in the ledger, deduplicates them, detects the tech stack and blacklisted titles, then writes two CSV files.

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

### `run_pipeline.py`

Recommended entry point. Runs `fetch_gmail` → `rename_eml` → `extract_eml` in sequence.

```bash
python3 run_pipeline.py            # full pipeline
python3 run_pipeline.py --dry-run  # simulate all three steps
```

Fail-fast: the pipeline stops at the first step that raises, so a later step never runs against a state left inconsistent by an earlier failure.

---

## Gmail OAuth2 setup

`fetch_gmail.py` needs a Google Cloud project with the Gmail API enabled and a one-time OAuth2 authorization (`credentials.json` and `token.json`, both git-ignored). See `docs/setup_gmail_auth.md` for the full walkthrough, including the "Access blocked" testing-mode pitfall and how to verify a silent token refresh.

---

## Configuration

### `config/config.json`

| Key | Role |
|-----|------|
| `offres_csv_headers` | order of CSV columns |
| `stack_keywords` | keywords used to detect the tech stack |
| `ville_dept` | city → département number mapping |
| `blacklist_titres` | titles to auto-flag (e.g. "nounou", "garde d'enfant") |

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

**Import:** Data → Import → Append to current sheet, selecting `output/import_YYYYMMDD.csv`.

**Conditional formatting** (set up once, range `A2:U`):

| Priority | Color | Formula | Meaning |
|----------|-------|---------|---------|
| 1 (high) | Yellow | `=$H2<>""` | Duplicate |
| 2 | Red | `=ISNUMBER(SEARCH("Blacklist";$T2))` | Blacklisted |

> Reference columns: A=ID, B=Traite, C=Date_decouverte, D=Source, E=Titre, F=Entreprise, G=Cle_dedup, H=Doublon_ID, I=Ville, J=Dept, K=Type_contrat, L=Salaire_min, M=Salaire_max, N=URL, O=URL_qualite, P=URL_redirect, Q=Stack, R=Raison_exclusion, S=Date_candidature, T=Notes, U=Message_ID
>
> Columns A through T are unchanged from before this pipeline's Gmail integration. `Message_ID` was appended as the last column (U) rather than inserted, so the conditional formatting formulas above (and any other formula referencing a lettered column) keep working without adjustment.

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
3. Implement `extract_<provider>(html, msg, patterns)` in `extract_eml.py`
4. Add it to the `EXTRACTORS` table
5. Test: `python3 extract_eml.py --dry-run`

---

## Roadmap

**Automating the Sheets import** was considered and deliberately deferred: writing offers directly via the Google Sheets API instead of the manual CSV import would require a new `spreadsheets` OAuth scope, handling partial writes to a live shared document, and would remove the visual-review safety net the manual import currently provides before offers land in the master tracking sheet. It stays out of scope for now, to revisit only once confidence in unattended extraction quality has been established over time - a separate project, not a pending task on this one.
