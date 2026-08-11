from unittest.mock import MagicMock

import pytest

from gmail_labeling import (
    LABEL_NAME,
    MAX_MESSAGES_PER_RUN,
    get_or_create_label,
    mark_processed,
    resolve_gmail_ids,
    run,
)


def test_resolve_gmail_ids_looks_up_gmail_id_per_message_id():
    ledger = {
        "<msg-1>": {"gmail_id": "abc123", "statut_extraction": "OK"},
        "<msg-2>": {"gmail_id": "def456", "statut_extraction": "PARTIEL"},
    }

    result = resolve_gmail_ids(ledger, ["<msg-1>", "<msg-2>"])

    assert result == ["abc123", "def456"]


def test_resolve_gmail_ids_excludes_sentinel_entries():
    ledger = {
        "<msg-1>": {"gmail_id": "abc123", "statut_extraction": "OK"},
        "<msg-2>": {"gmail_id": "before_gmail_api", "statut_extraction": "OK"},
        "<msg-3>": {"gmail_id": "manual", "statut_extraction": "OK"},
    }

    result = resolve_gmail_ids(ledger, ["<msg-1>", "<msg-2>", "<msg-3>"])

    assert result == ["abc123"]


def test_resolve_gmail_ids_skips_message_ids_absent_from_ledger():
    ledger = {"<msg-1>": {"gmail_id": "abc123", "statut_extraction": "OK"}}

    result = resolve_gmail_ids(ledger, ["<msg-1>", "<unknown>"])

    assert result == ["abc123"]


def test_get_or_create_label_returns_existing_label_id():
    service = MagicMock()
    service.users.return_value.labels.return_value.list.return_value.execute.return_value = {
        "labels": [{"id": "Label_1", "name": "Other"}, {"id": "Label_2", "name": LABEL_NAME}]
    }

    result = get_or_create_label(service)

    assert result == "Label_2"
    service.users.return_value.labels.return_value.create.assert_not_called()


def test_get_or_create_label_creates_when_missing():
    service = MagicMock()
    service.users.return_value.labels.return_value.list.return_value.execute.return_value = {
        "labels": [{"id": "Label_1", "name": "Other"}]
    }
    service.users.return_value.labels.return_value.create.return_value.execute.return_value = {
        "id": "Label_new",
        "name": LABEL_NAME,
    }

    result = get_or_create_label(service)

    assert result == "Label_new"
    service.users.return_value.labels.return_value.create.assert_called_once()


def test_mark_processed_adds_label_and_removes_unread_and_inbox():
    service = MagicMock()

    mark_processed(service, gmail_id="abc123", label_id="Label_2")

    service.users.return_value.messages.return_value.modify.assert_called_once_with(
        userId="me",
        id="abc123",
        body={"addLabelIds": ["Label_2"], "removeLabelIds": ["UNREAD", "INBOX"]},
    )


def test_run_refuses_when_over_the_safety_cap(monkeypatch):
    ledger = {
        f"<msg-{i}>": {"gmail_id": f"gid{i}", "statut_extraction": "OK"}
        for i in range(MAX_MESSAGES_PER_RUN + 1)
    }
    monkeypatch.setattr("gmail_labeling.load_ledger", lambda _path: ledger)

    with pytest.raises(RuntimeError, match=str(MAX_MESSAGES_PER_RUN)):
        run(list(ledger.keys()), dry_run=True)


def test_run_never_calls_trash_delete_or_send(monkeypatch):
    ledger = {"<msg-1>": {"gmail_id": "abc123", "statut_extraction": "OK"}}
    monkeypatch.setattr("gmail_labeling.load_ledger", lambda _path: ledger)
    service = MagicMock()
    service.users.return_value.labels.return_value.list.return_value.execute.return_value = {
        "labels": [{"id": "Label_2", "name": LABEL_NAME}]
    }
    monkeypatch.setattr("gmail_labeling.get_gmail_service", lambda: service)

    run(["<msg-1>"], dry_run=False)

    service.users.return_value.messages.return_value.modify.assert_called_once()
    service.users.return_value.messages.return_value.trash.assert_not_called()
    service.users.return_value.messages.return_value.delete.assert_not_called()
    service.users.return_value.messages.return_value.batchDelete.assert_not_called()
    service.users.return_value.messages.return_value.send.assert_not_called()
