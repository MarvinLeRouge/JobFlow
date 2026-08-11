from unittest.mock import MagicMock

from gmail_cleanup import (
    known_processed_gmail_ids,
    list_labeled_message_ids,
    run,
    trash_message,
)


def test_known_processed_gmail_ids_includes_ok_and_partiel():
    ledger = {
        "<msg-1>": {"gmail_id": "abc", "statut_extraction": "OK"},
        "<msg-2>": {"gmail_id": "def", "statut_extraction": "PARTIEL"},
    }

    assert known_processed_gmail_ids(ledger) == {"abc", "def"}


def test_known_processed_gmail_ids_excludes_pending():
    ledger = {"<msg-1>": {"gmail_id": "abc", "statut_extraction": "PENDING"}}

    assert known_processed_gmail_ids(ledger) == set()


def test_known_processed_gmail_ids_excludes_erreur():
    ledger = {"<msg-1>": {"gmail_id": "abc", "statut_extraction": "ERREUR"}}

    assert known_processed_gmail_ids(ledger) == set()


def test_known_processed_gmail_ids_excludes_sentinel_entries():
    ledger = {
        "<msg-1>": {"gmail_id": "before_gmail_api", "statut_extraction": "OK"},
        "<msg-2>": {"gmail_id": "manual", "statut_extraction": "OK"},
    }

    assert known_processed_gmail_ids(ledger) == set()


def test_list_labeled_message_ids_single_page():
    service = MagicMock()
    messages_resource = service.users.return_value.messages.return_value
    first_request = MagicMock()
    first_request.execute.return_value = {"messages": [{"id": "a"}, {"id": "b"}]}
    messages_resource.list.return_value = first_request
    messages_resource.list_next.return_value = None

    assert list_labeled_message_ids(service, "Label_2") == ["a", "b"]
    messages_resource.list.assert_called_once_with(userId="me", labelIds=["Label_2"])


def test_list_labeled_message_ids_paginates_across_multiple_pages():
    service = MagicMock()
    messages_resource = service.users.return_value.messages.return_value

    first_request = MagicMock()
    first_request.execute.return_value = {"messages": [{"id": "a"}], "nextPageToken": "tok"}
    second_request = MagicMock()
    second_request.execute.return_value = {"messages": [{"id": "b"}]}

    messages_resource.list.return_value = first_request
    messages_resource.list_next.side_effect = [second_request, None]

    result = list_labeled_message_ids(service, "Label_2")

    assert result == ["a", "b"]


def test_list_labeled_message_ids_no_results():
    service = MagicMock()
    messages_resource = service.users.return_value.messages.return_value
    request = MagicMock()
    request.execute.return_value = {}
    messages_resource.list.return_value = request
    messages_resource.list_next.return_value = None

    assert list_labeled_message_ids(service, "Label_2") == []


def test_trash_message_calls_trash_endpoint():
    service = MagicMock()

    trash_message(service, "abc123")

    service.users.return_value.messages.return_value.trash.assert_called_once_with(
        userId="me", id="abc123"
    )


def test_run_only_trashes_the_intersection_of_labeled_and_known_processed(monkeypatch):
    ledger = {
        "<msg-1>": {"gmail_id": "abc", "statut_extraction": "OK"},
        "<msg-2>": {"gmail_id": "def", "statut_extraction": "ERREUR"},
    }
    monkeypatch.setattr("gmail_cleanup.load_ledger", lambda _path: ledger)
    service = MagicMock()
    monkeypatch.setattr("gmail_cleanup.get_gmail_service", lambda: service)
    monkeypatch.setattr("gmail_cleanup.get_or_create_label", lambda _service: "Label_2")
    # "xyz" carries the label but is unknown to the ledger (e.g. applied
    # by hand by the user to an unrelated email) - must never be trashed.
    monkeypatch.setattr(
        "gmail_cleanup.list_labeled_message_ids", lambda _service, _label_id: ["abc", "def", "xyz"]
    )
    trashed = []
    monkeypatch.setattr(
        "gmail_cleanup.trash_message", lambda _service, gmail_id: trashed.append(gmail_id)
    )

    run(dry_run=False)

    assert trashed == ["abc"]


def test_run_dry_run_trashes_nothing(monkeypatch):
    ledger = {"<msg-1>": {"gmail_id": "abc", "statut_extraction": "OK"}}
    monkeypatch.setattr("gmail_cleanup.load_ledger", lambda _path: ledger)
    service = MagicMock()
    monkeypatch.setattr("gmail_cleanup.get_gmail_service", lambda: service)
    monkeypatch.setattr("gmail_cleanup.get_or_create_label", lambda _service: "Label_2")
    monkeypatch.setattr(
        "gmail_cleanup.list_labeled_message_ids", lambda _service, _label_id: ["abc"]
    )
    trashed = []
    monkeypatch.setattr(
        "gmail_cleanup.trash_message", lambda _service, gmail_id: trashed.append(gmail_id)
    )

    run(dry_run=True)

    assert trashed == []


def test_run_never_calls_delete_batch_delete_or_send(monkeypatch):
    ledger = {"<msg-1>": {"gmail_id": "abc", "statut_extraction": "OK"}}
    monkeypatch.setattr("gmail_cleanup.load_ledger", lambda _path: ledger)
    service = MagicMock()
    service.users.return_value.labels.return_value.list.return_value.execute.return_value = {
        "labels": [{"id": "Label_2", "name": "Recherche emploi"}]
    }
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "abc"}]
    }
    service.users.return_value.messages.return_value.list_next.return_value = None
    monkeypatch.setattr("gmail_cleanup.get_gmail_service", lambda: service)

    run(dry_run=False)

    service.users.return_value.messages.return_value.trash.assert_called_once()
    service.users.return_value.messages.return_value.delete.assert_not_called()
    service.users.return_value.messages.return_value.batchDelete.assert_not_called()
    service.users.return_value.messages.return_value.send.assert_not_called()
    service.users.return_value.messages.return_value.modify.assert_not_called()
