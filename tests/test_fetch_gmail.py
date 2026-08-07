import re
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from fetch_gmail import (
    build_filename,
    build_query,
    collect_sender_domains,
    compute_after_date,
    determine_after_date,
    list_message_ids,
    slugify_subject,
)


def test_collect_sender_domains_excludes_skip_entries_and_dedupes():
    patterns = {
        "_comment": "ignored",
        "indeed_alerte": {"sender_domains": ["jobalert.indeed.com", "indeed.com"]},
        "indeed_match": {"sender_domains": ["match.indeed.com"]},
        "meteojob_company": {"sender_domains": ["meteojob.com"]},
        "meteojob_digest": {"sender_domains": ["meteojob.com"], "skip": True},
    }
    assert collect_sender_domains(patterns) == [
        "indeed.com",
        "jobalert.indeed.com",
        "match.indeed.com",
        "meteojob.com",
    ]


def test_build_query_combines_senders_and_date():
    query = build_query(["indeed.com", "linkedin.com"], "2026/08/05")
    assert query == "({from:indeed.com from:linkedin.com}) after:2026/08/05"


def test_build_query_raises_on_empty_senders():
    with pytest.raises(ValueError):
        build_query([], "2026/08/05")


def test_compute_after_date_applies_overlap_margin():
    last_fetch = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)
    assert compute_after_date(last_fetch) == "2026/08/06"


def test_compute_after_date_rolls_back_a_day_across_midnight():
    last_fetch = datetime(2026, 8, 6, 2, 0, tzinfo=UTC)
    assert compute_after_date(last_fetch) == "2026/08/05"


def test_determine_after_date_uses_last_fetch_from_ledger():
    ledger = {
        "<msg-1>": {"gmail_id": "abc", "fetched_at": "2026-08-01T10:00:00Z"},
        "<msg-2>": {"gmail_id": "def", "fetched_at": "2026-08-05T09:00:00Z"},
        "<msg-3>": {"gmail_id": "before_gmail_api", "fetched_at": "2020-01-01T00:00:00Z"},
    }
    assert determine_after_date(ledger, since_days=None) == "2026/08/05"


def test_determine_after_date_falls_back_to_since_days_when_ledger_empty():
    result = determine_after_date({}, since_days=30)
    assert re.match(r"^\d{4}/\d{2}/\d{2}$", result)


def test_determine_after_date_raises_without_history_or_since_days():
    with pytest.raises(ValueError):
        determine_after_date({}, since_days=None)


def test_build_filename_includes_gmail_id_and_slug():
    assert build_filename("18d4a2f", "3 nouvelles offres !") == "18d4a2f-3-nouvelles-offres.eml"


def test_build_filename_is_unique_for_identical_subjects_via_gmail_id():
    a = build_filename("id-1", "Alerte emploi")
    b = build_filename("id-2", "Alerte emploi")
    assert a != b


def test_slugify_subject_handles_accents_and_empty():
    assert slugify_subject("Café à Paris") == "caf-paris"
    assert slugify_subject("") == "sans-sujet"


def test_list_message_ids_single_page():
    service = MagicMock()
    messages_resource = service.users.return_value.messages.return_value
    first_request = MagicMock()
    first_request.execute.return_value = {"messages": [{"id": "a"}, {"id": "b"}]}
    messages_resource.list.return_value = first_request
    messages_resource.list_next.return_value = None

    assert list_message_ids(service, "some query") == ["a", "b"]


def test_list_message_ids_paginates_across_multiple_pages():
    service = MagicMock()
    messages_resource = service.users.return_value.messages.return_value

    first_request = MagicMock()
    first_request.execute.return_value = {"messages": [{"id": "a"}], "nextPageToken": "tok"}
    second_request = MagicMock()
    second_request.execute.return_value = {"messages": [{"id": "b"}]}

    messages_resource.list.return_value = first_request
    messages_resource.list_next.side_effect = [second_request, None]

    result = list_message_ids(service, "some query")

    assert result == ["a", "b"]
    assert messages_resource.list_next.call_count == 2


def test_list_message_ids_no_results():
    service = MagicMock()
    messages_resource = service.users.return_value.messages.return_value
    request = MagicMock()
    request.execute.return_value = {}
    messages_resource.list.return_value = request
    messages_resource.list_next.return_value = None

    assert list_message_ids(service, "some query") == []
