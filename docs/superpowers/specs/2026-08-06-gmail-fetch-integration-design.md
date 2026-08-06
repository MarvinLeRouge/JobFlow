# Gmail Fetch Integration — Design

Date: 2026-08-06
Status: Approved (pending final review), ready for implementation planning

## Context

The job-search tracking pipeline currently requires manually downloading `.eml`
alert files from Gmail and dropping them into `sources/<provider>/` before
running `rename_eml.py` then `extract_eml.py`. This design automates the
download step via the Gmail API (OAuth2), integrates it into the existing
pipeline, and extends the existing per-email tracking to cover the new step
without duplicating state.

## Goals

- Automate `.eml` retrieval from Gmail via API (OAuth2, `gmail.readonly` scope).
- Preserve the existing dedup/extraction guarantees; add no new failure modes
  that could corrupt `output/offres.csv` or the tracking state.
- Keep the manual Sheets import step (explicit user choice — visual control
  before injecting into the master tracking document).
- No over-engineering: no queue, no database, no containerization. Local,
  manual execution, low volume (tens of files per run at most).

## Architecture

```
fetch_gmail.py           new: queries Gmail API, downloads new .eml
        |
sources/<provider>/      direct write, routed via providers.py
        |
rename_eml.py             modified: renames + writes to the unified ledger
        |
extract_eml.py             modified: reads/updates the ledger, offers gain
                            a Message_ID back-reference
        |
output/import_YYYYMMDD.csv   unchanged, manual import into Sheets

run_pipeline.py           orchestrates the three steps in sequence,
                           fail-fast, aggregated logs
providers.py               shared module: sender domain -> folder mapping
                            (extracted from rename_eml.py, used by both
                            fetch_gmail.py and rename_eml.py)
```

## Components

### `email_ledger.json` (replaces `logs/eml_index.csv`)

One record per email. `message_id` (RFC5322 header) is the primary,
durable key — it is intrinsic to the `.eml` file itself. `gmail_id` is a
secondary, nullable field: it only has meaning relative to the Gmail source
and would not exist if another mail source were added later.

Top-level structure: a single JSON object keyed by `message_id` (mirrors
the in-memory dict already built by the current `load_index()` in
`rename_eml.py`, just persisted as JSON instead of reconstructed from CSV
rows on each load):

```json
{
  "<message-id-1>": {
    "gmail_id": "18d4a2f...",
    "fichier": "indeed/20260806-1032-....eml",
    "date_email": "2026-08-06T10:32:00+0200",
    "fetched_at": "2026-08-06T10:35:12Z",
    "indexed_at": "2026-08-06T10:35:12Z",
    "statut_extraction": "PENDING"
  }
}
```

`gmail_id` is empty/absent for historical entries migrated from
`eml_index.csv` (those emails were never fetched via the API).

### `offres.csv` — traceability

New column `Message_ID`, a foreign key back to `email_ledger.json`. This is
a simple 1-email-to-N-offers relationship, so a foreign key on the "many"
side (the offer) is sufficient — no separate join file needed. Historical
rows keep this column empty (no retroactive reconstruction).

### `providers.py` (new shared module)

Extracted from `rename_eml.py`: `load_domain_map()` and `expected_folder()`.
Used by:
- `fetch_gmail.py`, to route each downloaded email to the correct
  `sources/<provider>/` folder at write time.
- `rename_eml.py --check`, unchanged behavior, now importing instead of
  defining the mapping locally.

Folder placement remains organizational only — `extract_eml.py` determines
the provider from the sender domain found in the email content itself, not
from the folder path, so misrouting (unlikely, since both steps share the
same mapping) would not break extraction.

### `fetch_gmail.py` (new)

- Builds the Gmail query by combining sender domains from
  `config/scraping_patterns.json` (`sender_domains` across all non-skip
  providers, reused as-is — no separate/duplicated senders list) with an
  `after:` date filter derived from the last successful fetch date, plus a
  short overlap margin (a few hours) to absorb `after:`'s day-level
  granularity without relying on exact-timestamp precision.
- Paginates through `users.messages.list` (`nextPageToken`) defensively,
  even though normal volume (tens of files) never triggers a second page —
  cheap to handle now, avoids silently dropping messages after a long gap
  between runs.
- For each message not already present in `email_ledger.json` (matched by
  `gmail_id`), downloads the raw `.eml` and writes it as
  `<gmail_id>-<subject-slug>.eml` into the routed provider folder.
  Prefixing with `gmail_id` guarantees filename uniqueness by construction
  (Gmail IDs are unique) — no ad hoc dedup/collision logic needed at write
  time, even when two alert emails share a near-identical subject.
- Persists `email_ledger.json` once, at the end of a successful run — same
  pattern as the existing scripts. If a run crashes mid-fetch, the ledger
  update for that run is simply lost; the next run may re-download an
  already-fetched email under a new `gmail_id`-based filename, but
  `rename_eml.py`'s existing `Message-ID` dedup catches it and moves it to
  `sources/_duplicates/` — no corruption, just a wasted API call.

### `run_pipeline.py` (new)

Calls `fetch_gmail`, `rename_eml`, `extract_eml` as in-process Python
function calls (not subprocess) in sequence. Fail-fast: any step raising
stops the pipeline before the next step runs. `--dry-run` propagates to all
three. Aggregates each step's summary into one final report (messages
found/downloaded, renamed/duplicates, offers written/duplicates/blacklisted).

### One-shot migration script

Converts existing `logs/eml_index.csv` (~900 rows) into
`email_ledger.json`, preserving `Statut_extraction`, `Fichier`,
`Date_email`, `Date_indexation`; `gmail_id` left empty for all migrated
rows. Also adds the empty `Message_ID` column to the existing
`output/offres.csv` (~1300+ rows).

## Authentication (handled separately, step-by-step)

Per explicit request, the OAuth2 setup is executed incrementally during
implementation, each step validated with an isolated minimal test before
moving to the next:

1. Google Cloud Console project creation
2. Gmail API activation
3. OAuth2 credentials creation
4. First authorization flow
5. `token.json` generation
6. Token refresh

Scope: `gmail.readonly`. `token.json` and OAuth client credentials are
never committed — added to `.gitignore`.

## Error handling

- Expired token / network error during fetch → pipeline stops before
  `rename_eml.py` runs; `email_ledger.json` is untouched (no partial write).
- No new emails found → normal run, 0 downloaded, clear log line, pipeline
  continues to rename/extract in case there is already pending work.
- Duplicate despite a lost ledger update (crash mid-fetch) → absorbed by
  the existing `Message-ID` dedup in `rename_eml.py`.

## Testing

No Python test infrastructure exists in the project today (no `pytest`, no
`requirements.txt`, no `tests/` directory — `sources/tests/<provider>/`
holds `.eml` fixtures only, not test code). This design introduces one,
matching the user's usual Python setup:

- `pytest` for tests, `ruff` for linting, `ruff-format` for formatting, all
  wired into a `pre-commit` hook for consistency with other projects (even
  if used sparingly on this one).
- `requirements.txt` (runtime: `google-api-python-client`,
  `google-auth-oauthlib`, `google-auth-httplib2`, `requests`) and
  `requirements-dev.txt` (`pytest`, `ruff`, `pre-commit`).
- `tests/test_providers.py` — domain-to-folder mapping resolution
  (including the suffix-matching fallback already used by
  `expected_folder()`).
- `tests/test_fetch_gmail.py` — Gmail query construction (senders + date +
  overlap margin, including a day-boundary edge case), pagination across
  multiple mocked pages, filename generation/collision-freedom. No live
  Gmail API calls — responses mocked via `unittest.mock`.
- `tests/test_ledger_migration.py` — conversion from `eml_index.csv`,
  including rows missing `Statut_extraction` (mirrors the existing
  migration fallback already present in `load_index()`).
- Coverage target: happy path + edge cases per each component (empty
  sender list, empty ledger, multi-page pagination, missing/malformed
  fields) — no error-state testing for scenarios that cannot occur (e.g.
  malformed OAuth tokens are Google's concern, not ours to unit-test).
- `.pre-commit-config.yaml`: `ruff` + `ruff-format` hooks (fast, run on
  every commit). `pytest` is run manually (`pytest tests/`), not wired into
  the commit hook, to keep commits fast — can be revisited if desired.

## Documentation

- `README.md` (English) and `README.fr.md` (French) — both kept in sync
  going forward, switching this project to the same convention as other
  projects (previously French-only, no functional reason to diverge once
  raised).
  - Updated pipeline diagram (fetch → sources/provider → rename → extract
    → import).
  - New sections for `fetch_gmail.py` and `run_pipeline.py` (usage, flags),
    matching the style of the existing `rename_eml.py`/`extract_eml.py`
    sections.
  - `email_ledger.json` format documented, replacing the current
    `eml_index.csv` description.
  - Testing section: how to run `pytest`, `ruff check`, `ruff format`, and
    how the `pre-commit` hook is installed.
  - One-line pointer to `docs/setup_gmail_auth.md` for OAuth2 setup detail.
- `docs/setup_gmail_auth.md` (new) — step-by-step OAuth2 walkthrough (Cloud
  Console → API activation → credentials → first auth flow → `token.json`
  → refresh), each step paired with its validation test, produced
  incrementally during implementation as each step is actually completed
  and verified.

## Roadmap (explicitly out of scope for this project)

- **Automating the Sheets import** (Point 6, option B): direct writes via
  the Google Sheets API instead of manual CSV import. Would require a new
  `spreadsheets` OAuth scope, handling partial writes to a live shared
  document, and would remove the visual-review safety net currently valued
  by the user. Revisit only once confidence in unattended extraction
  quality is established over time — a separate project, not bundled here.

## Out of scope / explicitly not addressed

- `sources/pdf/` and `sources/journal/` — external/legacy content, to be
  investigated separately by the user, unrelated to this pipeline.
- `hellowork` extractor (`EXTRACTORS["hellowork"] = None`) — pre-existing
  gap, unaffected by this change.
