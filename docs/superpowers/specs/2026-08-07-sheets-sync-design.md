# Automated Google Sheets Sync — Design

Date: 2026-08-07
Status: Approved (pending final review), ready for implementation planning

## Context

The job-search tracking pipeline (`fetch_gmail.py` → `rename_eml.py` → `extract_eml.py`, orchestrated by `run_pipeline.py`) currently ends at `output/import_YYYYMMDD.csv`: a manual step where the user opens Google Sheets and imports the file (`Données → Importer → Ajouter aux données actuelles`). This was a deliberate choice in the original Gmail fetch integration design, for visual control before writing to the live tracking sheet.

Since then, the pipeline has been validated end to end against real data (118 emails fetched, 565 offers extracted and manually imported with zero issues), and the user now wants the Sheets step automated too — closing the loop so `run_pipeline.py` becomes the single command that takes a fresh Gmail inbox all the way to an updated tracking sheet, formatting included.

The live sheet carries manual bookkeeping the automation must reproduce faithfully:
- Column B (`Traite`) is a 3-state dropdown (`FALSE` / `TRUE` / `"En cours"`, each with its own color) combined with a formula: new rows default to a computed value (`TRUE` when the row is blacklisted, based on the blacklist marker elsewhere in the row; otherwise left for manual triage), which the user can override by picking a different dropdown value — overwriting the formula with a static value, standard Sheets behavior.
- Row-level conditional formatting highlights duplicates and blacklisted offers by background color. The user has observed Sheets silently shrinking a manually-set wide formatting range back down to the actual data extent, so today this requires periodic manual re-widening.

## Goals

- Fold Sheets synchronization into `run_pipeline.py` as its final step, running automatically by default (no manual import step left).
- Faithfully reproduce column B's formula/dropdown behavior and the row-level conditional formatting on every newly-synced row, without the manual range-widening problem.
- Support a safe `--dry-run` (preview without writing), consistent with every other step in the pipeline.
- No over-engineering: no queue, no database, no new persistent state beyond a small error marker (see Error Handling).

## Architecture

```
extract_eml.py → output/import_YYYYMMDD.csv (unchanged)
        ↓
sheets_sync.py → compares the highest offer ID already present in the target sheet
                  against the import CSV's IDs, appends only the rows the sheet
                  doesn't have yet (idempotent, self-healing — no separate state
                  file needed for "what was already synced"), writes cell values,
                  reapplies column B's formula/dropdown, and extends row-level
                  conditional formatting to cover exactly the newly written rows
        ↓
run_pipeline.py → fetch → rename → extract → sheets_sync (new final step),
                   --dry-run propagates to every step, real push is the default
```

## Components

### `auth.py` (generalized, not duplicated)

Currently hardcodes `SCOPES` (`gmail.readonly`) and a single `TOKEN_FILE`. Generalized to accept `scopes: list[str]` and `token_file: Path` as parameters to `get_credentials()`, so `fetch_gmail.py` and `sheets_sync.py` each request their own least-privilege token (`token.json` for Gmail, `token_sheets.json` for the new `https://www.googleapis.com/auth/spreadsheets` scope) from the same `credentials.json` OAuth client — no second Cloud Console client registration needed, just a second consent grant for the new scope.

### `sheets_sync.py` (new)

- Reads the target `spreadsheet_id` from config (externalized — switching between the duplicate test sheet and the real one during development, and between them at any time afterward, is a one-line config change, never a code change).
- Reads the highest offer ID currently present in the target sheet's ID column, compares against `output/import_YYYYMMDD.csv`'s rows, and appends only the ones the sheet doesn't already have. IDs are fixed-width (`E006545`-style, always 6 zero-padded digits per `extract_eml.py`), so comparing the numeric suffix as an integer is unambiguous. This makes re-running `sheets_sync.py` (or `run_pipeline.py`) safe after a partial failure — already-synced rows are never re-appended.
- For each newly appended row: writes the cell values, and writes column B's discovered formula (see Phase 1 below) into that row specifically — with the formula's row-relative references adjusted to the new row's number, not a static computed value — so the blacklist-triggered auto-`TRUE` behavior and the manual dropdown override keep working exactly as today. Also applies/extends the row-level conditional formatting rules to cover exactly the new row range (sidestepping the range-shrinking problem by never relying on a static pre-set wide range).

### Phase 1 — Feasibility spike (on the user's duplicated sheet)

Before writing any production sync logic, a spike task reads the duplicated sheet via the Sheets API (`spreadsheets.get` with `fields` scoped to `conditionalFormats`, `dataValidation`, and cell formulas) to discover, verbatim:
- Column B's exact formula.
- The exact 3 dropdown values and their associated colors (data validation + conditional format rules).
- The exact row-level conditional formatting rules (duplicate/blacklist highlighting) and how they're currently expressed.

This avoids the user having to manually transcribe formulas/colors, and validates early that the Sheets API actually exposes everything needed before any production code is written against assumptions.

## Trigger and Gating

- `run_pipeline.py` calls `sheets_sync.run(dry_run=dry_run)` as its 4th and final step, same fail-fast pattern as the existing three steps.
- `--dry-run` on `sheets_sync.py` (standalone or via `run_pipeline.py`) computes and prints what would be appended (row count, ID range) without writing anything.
- Real push is the default when `--dry-run` is not passed, consistent with every other script in the pipeline. The user's stated rationale: Sheets keeps version history, so an unwanted automated write is recoverable, unlike the destructive-file risks addressed elsewhere in this pipeline (`ledger.py`, `migrate_offres_add_message_id.py`).

## Error Handling

- No automatic retry on a transient Sheets API error (network, quota) — matches the rest of the pipeline, which has no retry logic anywhere.
- On failure, `sheets_sync.py` writes a small persistent error-state file (timestamp, error message) rather than just letting the exception propagate and vanish.
- **Gate scope:** `run_pipeline.py` and `sheets_sync.py` both refuse to start (print the recorded error and stop) while this error-state file exists — the user must not lose track of an unresolved Sheets failure across later runs. `fetch_gmail.py`, `rename_eml.py`, and `extract_eml.py` remain usable individually even with a pending unacknowledged error, since blocking them would only hinder investigating the failure, not help.
- Acknowledgment clears the state: `sheets_sync.py --ack-error` (no separate acknowledgment script/tool).

## Data Flow / Idempotency

No new "already synced" tracking file. `sheets_sync.py` derives its own idempotency by reading the sheet's own current maximum offer ID and only appending rows from the import CSV with a strictly greater ID — the same check already performed manually earlier in this project ("is the last local ID really E005361") is now the automation's own safety mechanism, self-healing across retries without extra state to keep consistent.

## Testing

- `sheets_sync.py`'s ID-comparison/dedup logic and the error-gate check/acknowledge logic: unit-tested with a mocked Sheets API (`unittest.mock`), no real network calls — same convention as `fetch_gmail.py`'s test suite.
- The Phase 1 spike is validated manually against the real (duplicated) sheet, not via an automated test — same rationale as the OAuth2 live verification in the Gmail fetch integration (requires a real Google account and a real spreadsheet, not mockable in a meaningful way).
- No automated test writes to any real spreadsheet, test or production.

## Out of scope

- Any tab other than the offers tab (`candidatures.csv`, `entretiens.csv`, `journal_quotidien.csv`, `entreprises_cibles.csv` equivalents) — not addressed by this design.
- Retroactively fixing formatting on rows already in the sheet from before this automation existed — this design only ever touches newly appended rows.
