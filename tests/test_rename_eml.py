from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import rename_eml as rename_mod
from rename_eml import (
    LOCAL_TZ,
    build_new_name,
    check_folders,
    parse_headers,
    resolve_action,
    resolve_collision,
    run,
)


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


def test_build_new_name_formats_date_and_stem():
    dt = datetime(2026, 9, 18, 10, 30)
    assert build_new_name(dt, "raw") == "20260918-1030-raw.eml"


def test_resolve_collision_returns_the_plain_name_when_no_conflict(tmp_path):
    dt = datetime(2026, 9, 18, 10, 30)
    result = resolve_collision(tmp_path / "raw.eml", dt, "raw")
    assert result == tmp_path / "20260918-1030-raw.eml"


def test_resolve_collision_appends_a_counter_on_conflict(tmp_path):
    dt = datetime(2026, 9, 18, 10, 30)
    (tmp_path / "20260918-1030-raw.eml").write_text("existing", encoding="utf-8")

    result = resolve_collision(tmp_path / "raw.eml", dt, "raw")

    assert result == tmp_path / "20260918-1030-raw_2.eml"


def _write_eml(path: Path, message_id="<abc@example.com>", date="Fri, 18 Sep 2026 10:00:00 +0000"):
    lines = []
    if message_id is not None:
        lines.append(f"Message-ID: {message_id}")
    if date is not None:
        lines.append(f"Date: {date}")
    lines.append("Subject: Test")
    lines.append("")
    lines.append("body")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes("\r\n".join(lines).encode("utf-8"))


def test_parse_headers_returns_message_id_and_localized_datetime(tmp_path):
    eml_path = tmp_path / "raw.eml"
    _write_eml(eml_path)

    mid, dt = parse_headers(eml_path)

    assert mid == "<abc@example.com>"
    assert dt.tzinfo is not None
    assert dt.astimezone(LOCAL_TZ) == dt


def test_parse_headers_returns_none_message_id_when_missing(tmp_path):
    eml_path = tmp_path / "raw.eml"
    _write_eml(eml_path, message_id=None)

    mid, _dt = parse_headers(eml_path)

    assert mid is None


def test_parse_headers_returns_none_datetime_when_date_header_missing(tmp_path):
    eml_path = tmp_path / "raw.eml"
    _write_eml(eml_path, date=None)

    _mid, dt = parse_headers(eml_path)

    assert dt is None


def test_parse_headers_returns_none_none_on_read_error(tmp_path, capsys):
    unreadable = tmp_path / "weird.eml"
    unreadable.mkdir()

    mid, dt = parse_headers(unreadable)

    assert (mid, dt) == (None, None)
    assert "ERREUR lecture" in capsys.readouterr().err


def _setup_sources(tmp_path, monkeypatch):
    sources_dir = tmp_path / "sources"
    monkeypatch.setattr(rename_mod, "SOURCES_DIR", sources_dir)
    monkeypatch.setattr(rename_mod, "DUPES_DIR", sources_dir / "_duplicates")
    monkeypatch.setattr(rename_mod, "TESTS_DIR", sources_dir / "tests")
    monkeypatch.setattr(rename_mod, "LEDGER_FILE", tmp_path / "logs" / "email_ledger.json")
    return sources_dir


def test_check_folders_reports_when_no_domain_map(monkeypatch, capsys):
    with patch.object(rename_mod, "load_domain_map", return_value={}):
        check_folders()

    assert "Aucun mapping" in capsys.readouterr().err


def test_check_folders_reports_when_no_eml_files(tmp_path, monkeypatch, capsys):
    _setup_sources(tmp_path, monkeypatch)
    with patch.object(rename_mod, "load_domain_map", return_value={"indeed.com": "indeed"}):
        check_folders()

    assert "Aucun fichier .eml trouvé" in capsys.readouterr().out


def test_check_folders_reports_ok_for_a_correctly_placed_file(tmp_path, monkeypatch, capsys):
    sources_dir = _setup_sources(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    with (
        patch.object(rename_mod, "load_domain_map", return_value={"example.com": "indeed"}),
        patch.object(rename_mod, "sender_domain", return_value="example.com"),
    ):
        check_folders()

    out = capsys.readouterr().out
    assert "Aucun fichier mal placé" in out
    assert "1 OK" in out


def test_check_folders_reports_a_mismatch_for_a_wrongly_placed_file(tmp_path, monkeypatch, capsys):
    sources_dir = _setup_sources(tmp_path, monkeypatch)
    _write_eml(sources_dir / "wrong" / "raw.eml")
    with (
        patch.object(rename_mod, "load_domain_map", return_value={"example.com": "indeed"}),
        patch.object(rename_mod, "sender_domain", return_value="example.com"),
    ):
        check_folders()

    out = capsys.readouterr().out
    assert "MAUVAIS DOSSIER" in out
    assert "dossier attendu: indeed/" in out


def test_check_folders_reports_an_unknown_provider(tmp_path, monkeypatch, capsys):
    sources_dir = _setup_sources(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    with (
        patch.object(rename_mod, "load_domain_map", return_value={"example.com": "indeed"}),
        patch.object(rename_mod, "sender_domain", return_value="unknown-domain.example"),
    ):
        check_folders()

    out = capsys.readouterr().out
    assert "PROVIDER INCONNU" in out


def test_run_purge_reports_nothing_when_dupes_dir_is_empty_or_absent(tmp_path, monkeypatch, capsys):
    _setup_sources(tmp_path, monkeypatch)

    run(dry_run=False, purge=True)

    assert "vide ou absent" in capsys.readouterr().out


def test_run_purge_deletes_files_when_not_dry_run(tmp_path, monkeypatch, capsys):
    sources_dir = _setup_sources(tmp_path, monkeypatch)
    dupes_dir = sources_dir / "_duplicates"
    dupes_dir.mkdir(parents=True)
    (dupes_dir / "a.eml").write_text("a", encoding="utf-8")
    (dupes_dir / "b.eml").write_text("b", encoding="utf-8")

    run(dry_run=False, purge=True)

    assert list(dupes_dir.iterdir()) == []
    assert "Purge terminée" in capsys.readouterr().out


def test_run_purge_dry_run_does_not_delete_files(tmp_path, monkeypatch, capsys):
    sources_dir = _setup_sources(tmp_path, monkeypatch)
    dupes_dir = sources_dir / "_duplicates"
    dupes_dir.mkdir(parents=True)
    (dupes_dir / "a.eml").write_text("a", encoding="utf-8")

    run(dry_run=True, purge=True)

    assert len(list(dupes_dir.iterdir())) == 1


def test_run_reports_nothing_when_no_eml_files(tmp_path, monkeypatch, capsys):
    _setup_sources(tmp_path, monkeypatch)

    run(dry_run=False, purge=False)

    assert "Aucun fichier .eml trouvé" in capsys.readouterr().out


def test_run_renames_a_new_file_and_updates_the_ledger(tmp_path, monkeypatch, capsys):
    sources_dir = _setup_sources(tmp_path, monkeypatch)
    raw_path = sources_dir / "indeed" / "raw.eml"
    _write_eml(raw_path)
    dt = datetime(2026, 9, 18, 10, 30, tzinfo=LOCAL_TZ)

    with (
        patch.object(rename_mod, "parse_headers", return_value=("<msg-1>", dt)),
        patch.object(rename_mod, "load_ledger", return_value={}),
        patch.object(rename_mod, "save_ledger") as fake_save_ledger,
    ):
        run(dry_run=False, purge=False)

    new_path = sources_dir / "indeed" / "20260918-1030-raw.eml"
    assert new_path.exists()
    assert not raw_path.exists()
    fake_save_ledger.assert_called_once()
    saved_ledger = fake_save_ledger.call_args[0][1]
    assert saved_ledger["<msg-1>"]["fichier"] == "indeed/20260918-1030-raw.eml"
    assert "1 renommé" in capsys.readouterr().out


def test_run_dry_run_does_not_rename_or_save_the_ledger(tmp_path, monkeypatch, capsys):
    sources_dir = _setup_sources(tmp_path, monkeypatch)
    raw_path = sources_dir / "indeed" / "raw.eml"
    _write_eml(raw_path)
    dt = datetime(2026, 9, 18, 10, 30, tzinfo=LOCAL_TZ)

    with (
        patch.object(rename_mod, "parse_headers", return_value=("<msg-1>", dt)),
        patch.object(rename_mod, "load_ledger", return_value={}),
        patch.object(rename_mod, "save_ledger") as fake_save_ledger,
    ):
        run(dry_run=True, purge=False)

    assert raw_path.exists()
    fake_save_ledger.assert_not_called()
    assert "Simulation" in capsys.readouterr().out


def test_run_reindexes_an_already_prefixed_file_without_renaming(tmp_path, monkeypatch, capsys):
    sources_dir = _setup_sources(tmp_path, monkeypatch)
    prefixed_path = sources_dir / "indeed" / "20260918-1030-raw.eml"
    _write_eml(prefixed_path)
    dt = datetime(2026, 9, 18, 10, 30, tzinfo=LOCAL_TZ)

    with (
        patch.object(rename_mod, "parse_headers", return_value=("<msg-1>", dt)),
        patch.object(rename_mod, "load_ledger", return_value={}),
        patch.object(rename_mod, "save_ledger") as fake_save_ledger,
    ):
        run(dry_run=False, purge=False)

    assert prefixed_path.exists()
    saved_ledger = fake_save_ledger.call_args[0][1]
    assert saved_ledger["<msg-1>"]["fichier"] == "indeed/20260918-1030-raw.eml"
    assert "1 déjà préfixés/réindexés" in capsys.readouterr().out


def test_run_moves_a_duplicate_to_the_duplicates_dir(tmp_path, monkeypatch, capsys):
    sources_dir = _setup_sources(tmp_path, monkeypatch)
    raw_path = sources_dir / "indeed" / "raw.eml"
    _write_eml(raw_path)
    dt = datetime(2026, 9, 18, 10, 30, tzinfo=LOCAL_TZ)
    existing_ledger = {"<msg-1>": {"fichier": "indeed/20260601-0900-other.eml"}}

    with (
        patch.object(rename_mod, "parse_headers", return_value=("<msg-1>", dt)),
        patch.object(rename_mod, "load_ledger", return_value=existing_ledger),
        patch.object(rename_mod, "save_ledger") as fake_save_ledger,
    ):
        run(dry_run=False, purge=False)

    assert not raw_path.exists()
    assert (sources_dir / "_duplicates" / "raw.eml").exists()
    assert "1 doublon" in capsys.readouterr().out
    fake_save_ledger.assert_called_once()


def test_run_appends_a_counter_when_the_duplicates_dir_already_has_that_name(
    tmp_path, monkeypatch, capsys
):
    sources_dir = _setup_sources(tmp_path, monkeypatch)
    raw_path = sources_dir / "indeed" / "raw.eml"
    _write_eml(raw_path)
    dupes_dir = sources_dir / "_duplicates"
    dupes_dir.mkdir(parents=True)
    (dupes_dir / "raw.eml").write_text("already here", encoding="utf-8")
    dt = datetime(2026, 9, 18, 10, 30, tzinfo=LOCAL_TZ)
    existing_ledger = {"<msg-1>": {"fichier": "indeed/20260601-0900-other.eml"}}

    with (
        patch.object(rename_mod, "parse_headers", return_value=("<msg-1>", dt)),
        patch.object(rename_mod, "load_ledger", return_value=existing_ledger),
        patch.object(rename_mod, "save_ledger"),
    ):
        run(dry_run=False, purge=False)

    assert (dupes_dir / "raw_2.eml").exists()
    assert (dupes_dir / "raw.eml").read_text(encoding="utf-8") == "already here"


def test_run_skips_a_file_with_no_message_id(tmp_path, monkeypatch, capsys):
    sources_dir = _setup_sources(tmp_path, monkeypatch)
    raw_path = sources_dir / "indeed" / "raw.eml"
    _write_eml(raw_path)

    with (
        patch.object(rename_mod, "parse_headers", return_value=(None, None)),
        patch.object(rename_mod, "load_ledger", return_value={}),
        patch.object(rename_mod, "save_ledger"),
    ):
        run(dry_run=False, purge=False)

    assert raw_path.exists()
    assert "SKIP (Message-ID introuvable)" in capsys.readouterr().out


def test_run_skips_rename_when_date_is_missing(tmp_path, monkeypatch, capsys):
    sources_dir = _setup_sources(tmp_path, monkeypatch)
    raw_path = sources_dir / "indeed" / "raw.eml"
    _write_eml(raw_path)

    with (
        patch.object(rename_mod, "parse_headers", return_value=("<msg-1>", None)),
        patch.object(rename_mod, "load_ledger", return_value={}),
        patch.object(rename_mod, "save_ledger"),
    ):
        run(dry_run=False, purge=False)

    assert raw_path.exists()
    assert "SKIP (date introuvable)" in capsys.readouterr().out
