# ADR-0003: Automate Google Sheets sync as the pipeline's final step

- Status: Accepted
- Date: 2026-08-07
- Related PR: #6, #7

## Context

[ADR-0001](0001-automate-gmail-fetch-via-api.md) deliberately kept the
Google Sheets import manual, for visual control before writing to the live
tracking sheet. By 2026-08-07 the pipeline had been validated end to end
against real data (118 emails fetched, 565 offers extracted and manually
imported with zero issues), and the remaining manual step
(`Données -> Importer -> Ajouter aux données actuelles`) was now the only
gap between a fresh Gmail inbox and an updated tracking sheet.

## Decision

Fold Google Sheets synchronization into `run_pipeline.py` as its fourth and
final step, via a new `sheets_sync.py`, running automatically by default
(real push, not opt-in), consistent with every other step in the pipeline.
`--dry-run` is supported end to end, same as the rest of the pipeline.

## Consequences

- Supersedes the "keep Sheets import manual" decision recorded in
  [ADR-0001](0001-automate-gmail-fetch-via-api.md).
- Requires a new, separate OAuth scope
  (`https://www.googleapis.com/auth/spreadsheets`) and a second consent
  grant, handled by generalizing `auth.py` to accept `scopes` and
  `token_file` as parameters instead of hardcoding Gmail's.
- Removes the visual-review safety net that was the original rationale for
  the manual step; the ID-comparison idempotency
  ([ADR-0005](0005-idempotent-sync-via-max-id-comparison.md)) and the error
  gate ([ADR-0006](0006-persistent-error-gate.md)) are the mitigations put
  in its place.
- Real push as the default (rather than requiring an explicit flag) relies
  on Sheets' own version history for recoverability, unlike the
  destructive-file risks addressed elsewhere in the pipeline
  (`ledger.py`, `migrate_offres_add_message_id.py`).
