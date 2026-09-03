# Architecture Decision Records

Lightweight ADRs capturing the significant design decisions behind this
pipeline, extracted from the original design specs
(`docs/superpowers/specs/`, `docs/superpowers/plans/`, kept out of version
control, see `.gitignore`). English-only, like the changelog: a technical
audit trail, not reader-facing prose.

| ADR | Title | Date |
|---|---|---|
| [0001](0001-automate-gmail-fetch-via-api.md) | Automate Gmail alert retrieval via the Gmail API | 2026-08-06 |
| [0002](0002-json-ledger-keyed-by-message-id.md) | Track processed emails via a JSON ledger keyed by Message-ID | 2026-08-06 |
| [0003](0003-automate-sheets-sync.md) | Automate Google Sheets sync as the pipeline's final step | 2026-08-07 |
| [0004](0004-reproduce-sheet-formatting-via-reference-tab.md) | Reproduce Sheets formatting via a live reference tab | 2026-08-07 |
| [0005](0005-idempotent-sync-via-max-id-comparison.md) | Idempotent sync via max-ID comparison, no separate state file | 2026-08-07 |
| [0006](0006-persistent-error-gate.md) | Persistent error gate blocking the pipeline until acknowledged | 2026-08-07 |
