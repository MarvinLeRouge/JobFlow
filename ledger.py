"""Shared read/write access to logs/email_ledger.json, the per-email
tracking ledger used by fetch_gmail.py, rename_eml.py and extract_eml.py."""

import json
from pathlib import Path


def load_ledger(path: Path) -> dict:
    """Return the ledger as {message_id: record}. Empty dict if the file
    doesn't exist yet."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_ledger(path: Path, ledger: dict) -> None:
    """Persist the ledger as JSON, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2, sort_keys=True)
