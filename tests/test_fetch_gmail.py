import base64
import json
import re
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

import fetch_gmail as fetch
from fetch_gmail import (
    build_filename,
    build_query,
    collect_sender_domains,
    compute_after_date,
    determine_after_date,
    download_raw_eml,
    list_message_ids,
    load_patterns,
    run,
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


def test_load_patterns_reads_and_parses_the_patterns_file(tmp_path, monkeypatch):
    patterns_file = tmp_path / "scraping_patterns.json"
    patterns_file.write_text(
        json.dumps({"indeed_alerte": {"sender_domains": ["indeed.com"]}}), encoding="utf-8"
    )
    monkeypatch.setattr(fetch, "PATTERNS_FILE", patterns_file)

    assert load_patterns() == {"indeed_alerte": {"sender_domains": ["indeed.com"]}}


def test_download_raw_eml_decodes_the_base64_raw_payload():
    service = MagicMock()
    encoded = base64.urlsafe_b64encode(b"raw email content").decode("ascii")
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "raw": encoded
    }

    result = download_raw_eml(service, "gmail-id-1")

    assert result == b"raw email content"
    service.users.return_value.messages.return_value.get.assert_called_once_with(
        userId="me", id="gmail-id-1", format="raw"
    )


def _raw_eml(message_id="<abc@example.com>", from_addr="alerts@indeed.com", subject="Une offre"):
    lines = []
    if message_id is not None:
        lines.append(f"Message-ID: {message_id}")
    lines.append(f"From: {from_addr}")
    lines.append(f"Subject: {subject}")
    lines.append("Date: Fri, 18 Sep 2026 10:00:00 +0000")
    lines.append("")
    lines.append("body")
    return "\r\n".join(lines).encode("utf-8")


def _fake_service(gmail_id_to_raw: dict):
    service = MagicMock()
    messages_resource = service.users.return_value.messages.return_value

    list_request = MagicMock()
    list_request.execute.return_value = {"messages": [{"id": gid} for gid in gmail_id_to_raw]}
    messages_resource.list.return_value = list_request
    messages_resource.list_next.return_value = None

    def fake_get(**kwargs):
        request = MagicMock()
        encoded = base64.urlsafe_b64encode(gmail_id_to_raw[kwargs["id"]]).decode("ascii")
        request.execute.return_value = {"raw": encoded}
        return request

    messages_resource.get.side_effect = fake_get
    return service


PATTERNS = {"indeed_alerte": {"sender_domains": ["indeed.com"], "folder": "indeed"}}


def test_run_writes_new_email_and_updates_the_ledger(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetch, "SOURCES_DIR", tmp_path)
    fake_service = _fake_service({"gmail-1": _raw_eml()})

    with (
        patch.object(fetch, "load_patterns", return_value=PATTERNS),
        patch.object(fetch, "load_domain_map", return_value={"indeed.com": "indeed"}),
        patch.object(fetch, "load_ledger", return_value={}),
        patch.object(fetch, "determine_after_date", return_value="2026/09/01"),
        patch.object(fetch.auth, "get_credentials", return_value=object()),
        patch.object(fetch, "build", return_value=fake_service),
        patch.object(fetch, "save_ledger") as fake_save_ledger,
    ):
        run(dry_run=False)

    dest = tmp_path / "indeed" / "gmail-1-une-offre.eml"
    assert dest.exists()
    fake_save_ledger.assert_called_once()
    saved_ledger = fake_save_ledger.call_args[0][1]
    assert "<abc@example.com>" in saved_ledger
    assert saved_ledger["<abc@example.com>"]["gmail_id"] == "gmail-1"
    assert "1 email(s) téléchargé" in capsys.readouterr().out


def test_run_dry_run_does_not_write_files_or_the_ledger(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetch, "SOURCES_DIR", tmp_path)
    fake_service = _fake_service({"gmail-1": _raw_eml()})

    with (
        patch.object(fetch, "load_patterns", return_value=PATTERNS),
        patch.object(fetch, "load_domain_map", return_value={"indeed.com": "indeed"}),
        patch.object(fetch, "load_ledger", return_value={}),
        patch.object(fetch, "determine_after_date", return_value="2026/09/01"),
        patch.object(fetch.auth, "get_credentials", return_value=object()),
        patch.object(fetch, "build", return_value=fake_service),
        patch.object(fetch, "save_ledger") as fake_save_ledger,
    ):
        run(dry_run=True)

    assert not (tmp_path / "indeed").exists()
    fake_save_ledger.assert_not_called()
    assert "Simulation : 1 email(s) téléchargé" in capsys.readouterr().out


def test_run_skips_a_message_with_no_message_id(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetch, "SOURCES_DIR", tmp_path)
    fake_service = _fake_service({"gmail-1": _raw_eml(message_id=None)})

    with (
        patch.object(fetch, "load_patterns", return_value=PATTERNS),
        patch.object(fetch, "load_domain_map", return_value={"indeed.com": "indeed"}),
        patch.object(fetch, "load_ledger", return_value={}),
        patch.object(fetch, "determine_after_date", return_value="2026/09/01"),
        patch.object(fetch.auth, "get_credentials", return_value=object()),
        patch.object(fetch, "build", return_value=fake_service),
        patch.object(fetch, "save_ledger") as fake_save_ledger,
    ):
        run(dry_run=False)

    assert "SKIP (Message-ID introuvable)" in capsys.readouterr().out
    fake_save_ledger.assert_called_once()
    assert fake_save_ledger.call_args[0][1] == {}


def test_run_skips_a_message_already_known_under_another_gmail_id(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetch, "SOURCES_DIR", tmp_path)
    fake_service = _fake_service({"gmail-2": _raw_eml(message_id="<abc@example.com>")})
    existing_ledger = {
        "<abc@example.com>": {
            "gmail_id": "gmail-1",
            "fichier": "indeed/gmail-1-une-offre.eml",
            "date_email": "",
            "fetched_at": "2026-09-01T00:00:00Z",
            "indexed_at": "",
            "statut_extraction": "PENDING",
        }
    }

    with (
        patch.object(fetch, "load_patterns", return_value=PATTERNS),
        patch.object(fetch, "load_domain_map", return_value={"indeed.com": "indeed"}),
        patch.object(fetch, "load_ledger", return_value=existing_ledger),
        patch.object(fetch, "determine_after_date", return_value="2026/09/01"),
        patch.object(fetch.auth, "get_credentials", return_value=object()),
        patch.object(fetch, "build", return_value=fake_service),
        patch.object(fetch, "save_ledger") as fake_save_ledger,
    ):
        run(dry_run=False)

    assert "SKIP (déjà connu sous un autre gmail_id)" in capsys.readouterr().out
    fake_save_ledger.assert_called_once()
    assert fake_save_ledger.call_args[0][1] == existing_ledger


def test_run_skips_a_message_from_an_unknown_domain(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetch, "SOURCES_DIR", tmp_path)
    fake_service = _fake_service({"gmail-1": _raw_eml(from_addr="someone@unknown-domain.example")})

    with (
        patch.object(fetch, "load_patterns", return_value=PATTERNS),
        patch.object(fetch, "load_domain_map", return_value={"indeed.com": "indeed"}),
        patch.object(fetch, "load_ledger", return_value={}),
        patch.object(fetch, "determine_after_date", return_value="2026/09/01"),
        patch.object(fetch.auth, "get_credentials", return_value=object()),
        patch.object(fetch, "build", return_value=fake_service),
        patch.object(fetch, "save_ledger") as fake_save_ledger,
    ):
        run(dry_run=False)

    assert "SKIP (domaine inconnu: unknown-domain.example)" in capsys.readouterr().out
    fake_save_ledger.assert_called_once()
    assert fake_save_ledger.call_args[0][1] == {}


def test_run_skips_gmail_ids_already_present_in_the_ledger(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fetch, "SOURCES_DIR", tmp_path)
    fake_service = _fake_service({"gmail-1": _raw_eml()})
    existing_ledger = {
        "<other@example.com>": {
            "gmail_id": "gmail-1",
            "fichier": "indeed/gmail-1-other.eml",
            "date_email": "",
            "fetched_at": "2026-09-01T00:00:00Z",
            "indexed_at": "",
            "statut_extraction": "PENDING",
        }
    }

    with (
        patch.object(fetch, "load_patterns", return_value=PATTERNS),
        patch.object(fetch, "load_domain_map", return_value={"indeed.com": "indeed"}),
        patch.object(fetch, "load_ledger", return_value=existing_ledger),
        patch.object(fetch, "determine_after_date", return_value="2026/09/01"),
        patch.object(fetch.auth, "get_credentials", return_value=object()),
        patch.object(fetch, "build", return_value=fake_service),
        patch.object(fetch, "save_ledger") as fake_save_ledger,
    ):
        run(dry_run=False)

    assert "1 message(s) trouvé(s), 0 nouveau(x)" in capsys.readouterr().out
    fake_save_ledger.assert_called_once()
    assert fake_save_ledger.call_args[0][1] == existing_ledger
