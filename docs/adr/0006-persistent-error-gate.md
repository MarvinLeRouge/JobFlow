# ADR-0006: Persistent error gate blocking the pipeline until acknowledged

- Status: Accepted
- Date: 2026-08-07
- Related PR: #6, #7

## Context

Automated sync (see [ADR-0003](0003-automate-sheets-sync.md)) writes
directly to the live tracking sheet with no manual review step left. The
rest of the pipeline has no retry logic anywhere, so a transient Sheets API
error (network, quota) needed a way to surface and stay visible rather than
silently vanish after the exception propagated.

## Decision

On failure, `sheets_sync.py` writes a small persistent error-state file
(timestamp, error message). Both `run_pipeline.py` and `sheets_sync.py`
refuse to start (print the recorded error and stop) while this file
exists, so an unresolved Sheets failure cannot be silently skipped across
later runs. `fetch_gmail.py`, `rename_eml.py`, and `extract_eml.py` remain
usable individually even with a pending unacknowledged error, since
blocking them would only hinder investigating the failure, not help.
Acknowledgment clears the state via `sheets_sync.py --ack-error`, no
separate acknowledgment tool.

## Consequences

- Guarantees a failed sync is never silently skipped on the next scheduled
  run: the user must explicitly acknowledge it first.
- No automatic retry: a transient error still requires the user to notice
  and re-run manually, consistent with the rest of the pipeline having no
  retry logic anywhere.
- The gate has already caught a real incident in production: a sync crash
  went unacknowledged for a day, producing a 69-row gap between the local
  archive and the sheet, recovered manually and later covered by a
  general-purpose recovery tool (see
  [ADR-0005](0005-idempotent-sync-via-max-id-comparison.md), PR #22).
