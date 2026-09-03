[🇫🇷 Version française](SECURITY.fr.md) | 🇬🇧 English version

---

# Security Policy

## Supported Versions

This project has no maintained release branches: only the latest state of `main` is supported.

## Reporting a Vulnerability

Please report security vulnerabilities through GitHub's private vulnerability reporting: go to the [Security tab](https://github.com/MarvinLeRouge/JobFlow/security) of this repository and click "Report a vulnerability". Do not open a public issue for security reports.

This is a single-maintainer personal project: response times are best-effort, but reports will be acknowledged and investigated as soon as possible.

## Scope

In scope: the Python pipeline code in this repository (`fetch_gmail.py`, `rename_eml.py`, `extract_eml.py`, `sheets_sync.py`, `gmail_labeling.py`, `gmail_cleanup.py`, `run_pipeline.py`, and the `extract/` package) and its configuration handling.

Out of scope: the third-party services it integrates with (Gmail API, Google Sheets API, OpenStreetMap Nominatim) - report vulnerabilities in those services directly to their respective vendors.
