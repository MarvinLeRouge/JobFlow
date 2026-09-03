# ADR-0001: Automate Gmail alert retrieval via the Gmail API

- Status: Accepted
- Date: 2026-08-06
- Related PR: #2, #3, #4

## Context

The pipeline required manually downloading `.eml` alert files from Gmail and
dropping them into `sources/<provider>/` before running `rename_eml.py` then
`extract_eml.py`. This manual step was the main remaining friction in an
otherwise automated pipeline.

## Decision

Automate `.eml` retrieval via the Gmail API (OAuth2, `gmail.readonly` scope)
in a new `fetch_gmail.py` script, orchestrated together with the existing
steps by a new `run_pipeline.py`. The Gmail query combines sender domains
already defined in `config/scraping_patterns.json` with an `after:` date
filter derived from the last successful fetch, plus a short overlap margin
to absorb `after:`'s day-level granularity.

At this point, the Google Sheets import step was deliberately kept manual,
for visual control before writing to the live tracking sheet. This choice
was later revisited, see [ADR-0003](0003-automate-sheets-sync.md).

## Consequences

- No queue, no database, no containerization: local, manual-trigger
  execution, matching the pipeline's actual volume (tens of files per run).
- `token.json` and OAuth client credentials are never committed, added to
  `.gitignore`.
- A crash mid-fetch can cause an email to be re-downloaded under a new
  `gmail_id`-based filename on the next run; the existing Message-ID dedup
  in `rename_eml.py` absorbs this without corruption, at the cost of a
  wasted API call.
