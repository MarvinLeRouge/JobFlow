[🇫🇷 Version française](roadmap.fr.md) | 🇬🇧 English version

---

# Roadmap

**Automating the Sheets import** was implemented in `sheets_sync.py` (see the main [README](../README.md)). Offers now land directly in the master tracking sheet via the Google Sheets API, gated behind a persistent error state that blocks further syncs after a failed run until acknowledged, closing the gap this section used to describe as deliberately deferred.

**Cleaning up already-processed Gmail emails** was implemented in `gmail_cleanup.py` (see the main [README](../README.md)): a manually-triggered script that moves already-labeled emails to Trash, cross-checked against the local ledger rather than trusting the Gmail label alone.
