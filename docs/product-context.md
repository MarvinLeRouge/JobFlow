[🇫🇷 Version française](product-context.fr.md) | 🇬🇧 English version

---

# Product Context - JobFlow

## Concept

A job search on several platforms means up to a dozen alert emails a day, each provider with its own format, and the same posting relayed by several of them. JobFlow turns that inbox into one deduplicated, filtered and always-current Google Sheet: it fetches the alerts from Gmail, parses each provider's emails, merges duplicates across providers, excludes the offers that do not fit, appends the new rows to the sheet and archives the processed emails. The sheet then serves as the application tracker: contacts, application status, follow-ups.

## Target user

A single job seeker running the pipeline on their own machine, with their own Gmail account and their own tracking sheet. No multi-user support, no hosted service.

## Core vocabulary

| Term | Meaning |
|---|---|
| `provider` | A job platform sending alert emails, with one parser each: LinkedIn, Indeed, France Travail, Jobijoba, JobLeads, Meteojob, Talent.com (a new provider is one more parser module) |
| `ledger` | `logs/email_ledger.json`: every fetched email and its processing state (e.g. `PENDING`) |
| `Cle_dedup` | Cross-provider dedup key built from the normalized company, city and title, deliberately fuzzy |
| `Raison_exclusion` | Why an offer is excluded: `Hors profil` (title on the blacklist, e.g. a hotel manager position), `Stage/Alternance`, `Hors stack` |
| `error gate` | After a failed sync, every later run stops until the failure is acknowledged (`--ack-error`) |
| `Références tab` | The sheet tab whose formatting (dropdowns, colors) is copied onto every new row |

## Features

- **Gmail ingestion** - OAuth2 fetch of new alerts, routed per provider, incremental from the ledger
- **Per-provider parsing** - one regex-based parser per provider, not a generic scraper; extensible by adding a parser
- **Two-level deduplication** - by Message-ID for emails, by `Cle_dedup` for postings relayed by several providers
- **Exclusions** - off-profile titles, internships and apprenticeships, and offers outside the tech stack are excluded automatically; they stay in the sheet with their `Raison_exclusion`, so the decision remains visible
- **Location** - city resolved to its French département
- **Sheet sync** - new rows appended with the sheet's own formatting, protected by the error gate
- **Application tracking** - in the sheet: contacts for each application and its status (waiting, follow-up and so on)
- **Inbox cleanup** - processed emails marked as read, labeled and archived
- **Fail-fast pipeline** - `run_pipeline.py` chains the five stages and stops at the first failure

## Non-goals

- Scraping job sites: only the alert emails are read
- Sending applications on the user's behalf
- Automatic retry after a failed sync: a human acknowledges the error first
- A web interface: the Google Sheet is the interface
