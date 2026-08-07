from pathlib import Path

from rename_eml import resolve_action


def test_resolve_action_new_message_id_needs_rename():
    assert resolve_action("<msg-1>", Path("indeed/raw.eml"), "raw.eml", {}) == "rename"


def test_resolve_action_new_message_id_already_prefixed():
    action = resolve_action(
        "<msg-1>", Path("indeed/20260806-1032-raw.eml"), "20260806-1032-raw.eml", {}
    )
    assert action == "reindex"


def test_resolve_action_known_message_id_same_file_not_yet_renamed():
    ledger = {"<msg-1>": {"fichier": "indeed/abc123-raw.eml"}}
    action = resolve_action("<msg-1>", Path("indeed/abc123-raw.eml"), "abc123-raw.eml", ledger)
    assert action == "rename"


def test_resolve_action_known_message_id_same_file_already_renamed():
    ledger = {"<msg-1>": {"fichier": "indeed/20260806-1032-raw.eml"}}
    action = resolve_action(
        "<msg-1>", Path("indeed/20260806-1032-raw.eml"), "20260806-1032-raw.eml", ledger
    )
    assert action == "reindex"


def test_resolve_action_known_message_id_different_file_is_duplicate():
    ledger = {"<msg-1>": {"fichier": "indeed/20260601-0900-other.eml"}}
    action = resolve_action("<msg-1>", Path("indeed/raw.eml"), "raw.eml", ledger)
    assert action == "duplicate"
