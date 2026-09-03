# Changelog

All notable changes to this project are documented in this file, generated
from [Conventional Commits](https://www.conventionalcommits.org) history by
[git-cliff](https://git-cliff.org).

This project does not use tagged releases; commits are grouped
chronologically under "Unreleased". Automatically regenerated in CI on push
to `main` (see `.github/workflows/changelog.yml`). To regenerate locally,
run `git-cliff -o CHANGELOG.md`.

## [Unreleased]

### Features
- Initial commit
- Add providers module for sender domain routing
- Add ledger module for email_ledger.json read/write
- Add one-shot migration from eml_index.csv to email_ledger.json
- Add one-shot migration adding Message_ID to offres.csv
- Switch rename_eml.py to the unified email ledger
- Switch extract_eml.py to the unified email ledger, add Message_ID
- Add Gmail OAuth2 credential management
- Add fetch_gmail.py for automated .eml retrieval
- Add run_pipeline.py orchestrator
- Generalize auth.get_credentials for multiple scopes and tokens
- Add sheets_sync.py ID comparison and dedup core
- Add sheet formatting inspection spike script
- Add sheets_sync config section
- Add sheets_sync.py persistent error-state gate
- Write new rows and replicate column B/R formatting from References
- Extend conditional formatting ranges on sync
- Integrate sheets_sync as run_pipeline.py's final step
- Add sheets_sync.py standalone CLI entry point
- Add login-triggered daily pipeline prompt
- Add gmail_labeling module for post-processing Gmail state
- Wire gmail_labeling as the pipeline's 5th step
- Add manual Gmail cleanup script for already-labeled emails
- *(sheets)* Add manual sync recovery script for gap detection and backfill
- *(extract)* Simplify blacklist reason to a category in Raison_exclusion


### Bug Fixes
- Remove em dashes from migrate_eml_index_to_ledger.py
- Harden migrations and ledger writes, document migration steps, fix run_pipeline bootstrap
- Gitignore token_sheets.json
- Extend sheet grid before writing new rows
- Apply column R dropdown only to rows without a pre-filled reason
- Explicitly clear inherited column R validation on rows without a reason
- Prevent live Sheets API calls from unmocked run_pipeline tests
- Restore docs/ai/ gitignore rule mangled by prior append
- Always write headers on daily import_YYYYMMDD.csv files
- Stop committing the real spreadsheet ID, force-text Source/Dept
- Fall back to interactive re-auth when a refresh token is dead
- *(ci)* Use npx git-cliff instead of the Docker-based action


### Refactor
- Remove Statut column from offres pipeline
- Extract domain routing into providers module
- *(extract)* Split extract_eml.py into an extract/ package, add missing test coverage


### Documentation
- Update README for the Gmail fetch pipeline, add French translation
- Correct fetched_at description for migrated ledger entries
- Document sheets_sync.py and the updated pipeline
- Document Références tab fragility and two deferred minor findings
- Add ARCHITECTURE, MIT license, update READMEs for the extract/ package split
- Homogenize README style with other projects (bilingual header, badges, About)
- Document login_pipeline_check.py and its autostart setup
- Document gmail_labeling.py and the 5-step pipeline
- Document gmail_cleanup.py, close the Roadmap item
- Document the OAuth testing-mode 7-day token expiry and recovery
- Add ADRs distilled from the superpowers design specs, gitignore superpowers artifacts
- Fix diverging test count badges in README headers
- Remove stale one-time migration section from README
- Extract roadmap section from README into dedicated files
- Add CONTRIBUTING and CODE_OF_CONDUCT
- Add SECURITY policy
- Add operations runbook, extract OAuth2/autostart from README
- Add bilingual cross-link banner and French version of Gmail OAuth2 setup
- Remove stale docs/workflow.md
- Add GitHub PR and issue templates
- Add changelog automation via git-cliff


### Miscellaneous Tasks
- Add pytest/ruff/pre-commit tooling
- Apply Message_ID migration to config.json
- Gitignore local docs/ai working directory
- Untrack stray __pycache__/*.pyc files
- *(docs)* Update test count badge to 185


