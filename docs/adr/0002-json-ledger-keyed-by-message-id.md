# ADR-0002: Track processed emails via a JSON ledger keyed by Message-ID

- Status: Accepted
- Date: 2026-08-06
- Related PR: #2, #3, #4

## Context

Per-email tracking (which emails were seen, renamed, extracted) previously
lived in `logs/eml_index.csv`, keyed loosely and rebuilt into an in-memory
dict on every load. Automating Gmail fetch (see
[ADR-0001](0001-automate-gmail-fetch-via-api.md)) added a new source of
per-email identity (the Gmail message ID) that this tracking needed to
absorb without duplicating state or coupling the pipeline to Gmail
specifically.

## Decision

Replace `logs/eml_index.csv` with `logs/email_ledger.json`: a single JSON
object keyed by `message_id` (the RFC5322 header), the durable identity
intrinsic to the `.eml` file itself. `gmail_id` is stored as a secondary,
nullable field, meaningful only relative to the Gmail source. Historical
entries migrated from `eml_index.csv` get `gmail_id` set to the explicit
sentinel `"before_gmail_api"` rather than left empty, so "predates the API
integration" stays distinguishable at a glance from a future bug that fails
to populate the field.

## Consequences

- The ledger is not tied to Gmail as a source; a future second mail source
  would not need `gmail_id` at all.
- A one-shot migration script converts the existing `~900`-row
  `eml_index.csv` into the new ledger format.
- `output/offres.csv` gains a `Message_ID` column, a foreign key back to
  the ledger (one email to many offers, so a foreign key on the offer side
  is sufficient, no separate join file). Historical rows keep this column
  empty rather than being retroactively reconstructed.
