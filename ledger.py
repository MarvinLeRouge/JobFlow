"""Shared read/write access to logs/email_ledger.json, the per-email
tracking ledger used by fetch_gmail.py, rename_eml.py and extract_eml.py."""

import json
import os
from pathlib import Path


def load_ledger(path: Path) -> dict:
    """Return the ledger as {message_id: record}. Empty dict if the file
    doesn't exist yet."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_ledger(path: Path, ledger: dict) -> None:
    """Persist the ledger as JSON, creating parent directories if needed.

    The dump goes to a temp file in the same directory, then replaces the
    real file in one atomic move: an interruption mid-dump can never leave
    the ledger truncated or invalid, which would break every script that
    loads it on startup."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
