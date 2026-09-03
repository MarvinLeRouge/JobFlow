# ADR-0005: Idempotent sync via max-ID comparison, no separate state file

- Status: Accepted
- Date: 2026-08-07
- Related PR: #6, #7

## Context

Automated sync (see [ADR-0003](0003-automate-sheets-sync.md)) needs to know
which rows from `output/import_YYYYMMDD.csv` are already present in the
sheet, so a re-run after a partial failure does not duplicate rows. Offer
IDs are fixed-width (`E006545`-style, always 6 zero-padded digits, assigned
by `extract_eml.py`), so the numeric suffix can be compared unambiguously
as an integer.

## Decision

`sheets_sync.py` reads the highest offer ID currently present in the target
sheet's ID column and appends only the import rows with a strictly greater
ID. No separate "already synced" tracking file is introduced; the sheet's
own current state is the single source of truth for what has already been
written.

## Consequences

- Re-running `sheets_sync.py` or `run_pipeline.py` after a partial failure
  is safe by construction: already-synced rows are never re-appended.
- No extra state file to keep consistent with the sheet's real content.
- This same design was later reused by `sheets_sync_recovery.py` to detect
  and backfill any gap between the sheet and the local
  `output/offres.csv` archive, not just a lagging tail (see PR #22).
- The comparison only detects a lagging tail (rows below the current max
  ID missing from the sheet, e.g. an internal gap from a skipped row, are
  not caught by this mechanism alone).
