# Architecture

This document covers the *why* behind the main design choices. For usage and configuration, see [README.md](README.md).

---

## Pipeline: four independent, fail-fast stages

```
fetch_gmail.py → rename_eml.py → extract_eml.py → sheets_sync.py
```

Each stage is a standalone script with its own dry-run mode, driven by a single shared state file, `logs/email_ledger.json` (keyed by Message-ID), rather than by re-scanning `sources/` from scratch on every run. This makes every stage idempotent: re-running `rename_eml.py` or `extract_eml.py` after a partial failure only processes what the ledger still marks as pending, instead of reprocessing (and re-deduplicating, re-writing) everything.

`run_pipeline.py` chains the four stages and stops at the first one that raises, so a later stage never runs against a state left inconsistent by an earlier failure (e.g. `sheets_sync.py` never runs against an `import_YYYYMMDD.csv` that `extract_eml.py` only half-wrote).

---

## Provider parsers: one regex-based module per provider, not a generic scraper

`extract/providers/` has one file per job alert provider (France Travail, Indeed, LinkedIn, Meteojob, Jobijoba, Talent.com), each with its own hand-written regexes against that provider's specific HTML email template.

A generic, configuration-driven HTML scraper was not worth building: these are marketing emails, not a public API, and each provider's template has its own quirks that a shared abstraction would have to special-case anyway (see the inline comments in `extract/providers/*.py` — e.g. Jobijoba's redirect link opening *before* the title text it belongs to, or LinkedIn's company/location line sitting ~4200 characters after the job link in the raw HTML). Six small, independently testable functions turned out simpler than one flexible one.

---

## Deduplication: cross-provider, not just cross-email

`rename_eml.py` already deduplicates at the email level, by Message-ID: the same alert email can't be processed twice. That's not enough on its own, because the *same job posting* routinely gets sent by several providers at once (e.g. LinkedIn and Indeed both relaying the same listing).

`extract_eml.py` adds a second, cross-provider dedup key (`Cle_dedup`, see [README.md](README.md#deduplication)) built from the normalized company, city and a stop-word-stripped title slug — deliberately fuzzy (case/accent-insensitive, no punctuation) rather than an exact string match, since the same offer's title/company text is rarely byte-identical across two providers' templates.

---

## `extract/` package split

`extract_eml.py` used to be a single ~1100-line file mixing text cleaning, geo lookup, the six provider parsers, dedup/blacklist/stack filtering, and CSV/log IO. It's now split by responsibility (`text.py`, `filters.py`, `geo.py`, `io.py`, `providers/`), with `extract_eml.py` left as a thin orchestrator. The split was done test-first: characterization tests were written against the original monolithic file, then used as a regression safety net while moving code — see `tests/extract/`, which mirrors the package layout.

---

## `sheets_sync.py`'s error gate: block, don't retry-and-hope

On any failure, `sheets_sync.py` writes the error to `logs/sheets_sync_error.json` and every subsequent run (including through `run_pipeline.py`) refuses to sync again until a human runs `--ack-error`. It does not retry automatically, and it does not skip the failed run and continue with the next one.

The reasoning: a Sheets sync failure partway through a batch of rows is exactly the situation where "just try again next time" is dangerous — the sheet's own highest offer ID (used to compute which rows are missing) could be left in an ambiguous state, and silently re-attempting could append rows twice or skip them. Forcing an explicit acknowledgment trades a bit of friction for the guarantee that nobody looks at the tracking sheet believing it's current when a sync has actually been silently failing for days.

---

## The Références tab: a live dependency, not a one-time template

`sheets_sync.py` copies cell formatting (dropdowns, colors) from a dedicated "Références" tab onto every newly-appended row, on *every* sync run — not once at setup time. This is a workaround, not the original design: the Sheets API turned out not to expose conditional dropdown/validation *colors* at all, so live copy-paste from two known-good reference cells was the only reliable way to reproduce them. The trade-off is documented in [README.md](README.md#important-the-références-tab-is-a-live-dependency): the tab's structure becomes a silent dependency that nothing enforces or errors on if broken.

---

## Known trade-offs

- **City→département resolution** falls back to the Nominatim API (rate-limited to ~1 req/s, cached in-process) for cities not in the local `ville_dept` table. This is a soft dependency: it fails open (returns an empty département rather than blocking extraction) if Nominatim is unreachable.
- **Provider parsers are brittle by construction** — regex-based against emails a single person receives, not integration-tested against the providers' current templates. When a provider changes their email template, the fix is a new/updated test fixture in `tests/extract/providers/` plus a regex change, not a scraper rewrite.
