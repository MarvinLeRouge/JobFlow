# ADR-0004: Reproduce Sheets formatting via a live reference tab

- Status: Accepted
- Date: 2026-08-07
- Related PR: #6, #7

## Context

The live tracking sheet carries manual bookkeeping that automated sync
(see [ADR-0003](0003-automate-sheets-sync.md)) had to reproduce faithfully:
column B (`Traite`) is a 3-state dropdown, each value with its own fill
color, combined with a row formula; row-level conditional formatting
highlights duplicates and blacklisted offers by background color.

A feasibility spike read the duplicated sheet via the Sheets API
(`spreadsheets.get`, `fields` scoped to `conditionalFormats`,
`dataValidation`, and cell formulas) to transcribe this behavior before
writing production code against assumptions. The spike found, confirmed
with a fully unrestricted `fields` query, that dropdown/validation fill
colors are not exposed by the Sheets API at all: only the formula and the
validation rule itself are readable, not the colors tied to each dropdown
value. Transcribing colors verbatim into code, as originally planned, turned
out to be impossible.

## Decision

`copy_reference_formatting()` copies formatting directly from two reference
cells in a "Références" tab (`reference_row_b`, `reference_row_r`) onto
every newly-synced row via `copyPaste`, on every single sync run, not just
once at initial setup.

## Consequences

- The "Références" tab becomes a live, ongoing dependency rather than a
  one-time setup aid. Nothing in the sheet or the code enforces its
  internal structure: if the user reorders rows within it, or clears or
  changes the formatting/validation on the reference cells themselves,
  every future sync silently copies wrong or missing formatting onto new
  rows.
- This failure mode is not caught by the error gate
  ([ADR-0006](0006-persistent-error-gate.md)): `get_sheet_id()` only raises
  when a tab is renamed or deleted outright, it has no way to detect that a
  tab's internal row structure changed.
