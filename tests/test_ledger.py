import json

from ledger import load_ledger, save_ledger


def test_load_ledger_missing_file_returns_empty_dict(tmp_path):
    assert load_ledger(tmp_path / "email_ledger.json") == {}


def test_save_then_load_ledger_round_trips(tmp_path):
    path = tmp_path / "logs" / "email_ledger.json"
    ledger = {
        "<msg-1>": {
            "gmail_id": "abc123",
            "fichier": "indeed/20260806-1032-foo.eml",
            "date_email": "2026-08-06T10:32:00+0200",
            "fetched_at": "2026-08-06T10:35:12Z",
            "indexed_at": "2026-08-06T10:35:12Z",
            "statut_extraction": "PENDING",
        }
    }
    save_ledger(path, ledger)
    assert load_ledger(path) == ledger


def test_save_ledger_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "logs" / "email_ledger.json"
    save_ledger(path, {})
    assert path.exists()


def test_save_ledger_writes_valid_json(tmp_path):
    path = tmp_path / "email_ledger.json"
    save_ledger(path, {"<msg-1>": {"gmail_id": "before_gmail_api"}})
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    assert data == {"<msg-1>": {"gmail_id": "before_gmail_api"}}
