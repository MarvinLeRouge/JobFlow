[🇫🇷 Version française](operations.fr.md) | 🇬🇧 English version

---

# Operations

Day-to-day operational tasks for running this pipeline on your own machine: not code reference (see the main [README](../README.md) for that), but setup and recovery procedures.

## OAuth2 setup

**Gmail:** `fetch_gmail.py` needs a Google Cloud project with the Gmail API enabled and a one-time OAuth2 authorization (`credentials.json` and `token.json`, both git-ignored). See [docs/setup_gmail_auth.md](setup_gmail_auth.md) for the full walkthrough, including the "Access blocked" testing-mode pitfall and how to verify a silent token refresh.

**Google Sheets:** `sheets_sync.py` needs its own OAuth2 token, `token_sheets.json` (git-ignored), authorized with the `spreadsheets` scope. It reuses the same OAuth client as Gmail (`credentials.json`) but keeps a separate token file since the scopes differ. The first real run opens a browser for a one-time consent screen; after that, `auth.get_credentials()` refreshes the token silently, the same way it already does for Gmail.

**Gmail labeling:** `gmail_labeling.py` requires yet another token, `token_gmail_modify.json` (git-ignored), with the broader `gmail.modify` scope. Same one-time consent flow as above.

## Autostart (login-triggered pipeline check)

`login_pipeline_check.py` is an optional convenience layer on top of `run_pipeline.py`: it prompts once per calendar day to run the pipeline, meant to be launched automatically at graphical login rather than run manually. See the [`login_pipeline_check.py`](../README.md#login_pipeline_checkpy) section of the README for how it works.

**One-time local setup** (not managed by this repo): create an XDG autostart entry so a graphical login launches the check.

```
# ~/.config/autostart/jobflow-pipeline-check.desktop
[Desktop Entry]
Type=Application
Name=JobFlow pipeline check
Comment=Propose de lancer le pipeline JobFlow (une fois par jour maximum)
Exec=/usr/bin/python3 /path/to/JobFlow/login_pipeline_check.py
X-GNOME-Autostart-enabled=true
NoDisplay=true
Hidden=false
```

## Recovering from a sync failure

`sheets_sync.py` records any failure to `logs/sheets_sync_error.json` and refuses to run again (along with `run_pipeline.py`) until it is acknowledged:

```bash
python3 sheets_sync.py --ack-error
```

Because `sheets_sync.py` only ever looks at **today's** import CSV, an unacknowledged failure on one day followed by a normal run on a later day silently orphans that day's rows: they are never resynced, and nothing downstream notices the hole on its own. After acknowledging the error, check whether any rows were left behind and backfill them:

```bash
python3 sheets_sync_recovery.py --dry-run   # report only, no write
python3 sheets_sync_recovery.py             # backfill what's found
```

This compares every offer ID in the sheet against the local `output/offres.csv` archive and backfills anything missing, whether an internal gap or a lagging tail. See the [`sheets_sync_recovery.py`](../README.md#sheets_sync_recoverypy) section of the README for the full behavior (separator rows, idempotent reruns, what it refuses to touch).
