import csv
from unittest.mock import patch

import extract_eml as extract_mod
from extract_eml import get_eml_parts, load_config, load_patterns, main, resolve_write_headers


def test_resolve_write_headers_auto_always_writes_headers():
    write_headers, _ = resolve_write_headers(force_headers=None)
    assert write_headers is True


def test_resolve_write_headers_respects_forced_true():
    write_headers, _ = resolve_write_headers(force_headers=True)
    assert write_headers is True


def test_resolve_write_headers_respects_forced_false():
    write_headers, _ = resolve_write_headers(force_headers=False)
    assert write_headers is False


def test_load_config_reads_and_parses_the_config_file(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"a": 1}', encoding="utf-8")
    monkeypatch.setattr(extract_mod, "CONFIG_FILE", config_file)

    assert load_config() == {"a": 1}


def test_load_patterns_reads_and_parses_the_patterns_file(tmp_path, monkeypatch):
    patterns_file = tmp_path / "scraping_patterns.json"
    patterns_file.write_text('{"indeed": {}}', encoding="utf-8")
    monkeypatch.setattr(extract_mod, "PATTERNS_FILE", patterns_file)

    assert load_patterns() == {"indeed": {}}


def _write_eml(path, from_addr="alerts@example.com", subject="Une offre"):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"From: {from_addr}\r\n"
        f"Subject: {subject}\r\n"
        'Content-Type: multipart/alternative; boundary="BOUND"\r\n'
        "\r\n"
        "--BOUND\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        "texte brut\r\n"
        "--BOUND\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "\r\n"
        "<p>html body</p>\r\n"
        "--BOUND--\r\n"
    )
    path.write_bytes(content.encode("utf-8"))


def test_get_eml_parts_extracts_the_html_and_text_bodies(tmp_path):
    eml_path = tmp_path / "raw.eml"
    _write_eml(eml_path)

    msg, html, text = get_eml_parts(eml_path)

    assert msg.get("From") == "alerts@example.com"
    assert "<p>html body</p>" in html
    assert "texte brut" in text


HEADERS = [
    "ID",
    "Traite",
    "Date_decouverte",
    "Source",
    "Titre",
    "Entreprise",
    "Cle_dedup",
    "Doublon_ID",
    "Ville",
    "Dept",
    "Type_contrat",
    "Salaire_min",
    "Salaire_max",
    "URL",
    "URL_qualite",
    "URL_redirect",
    "Stack",
    "Raison_exclusion",
    "Date_candidature",
    "Notes",
    "Message_ID",
]

CONFIG = {
    "offres_csv_headers": HEADERS,
    "stack_keywords": {"python": ["python"], "php": ["php"]},
    "blacklist_titres": ["stage"],
    "stage_alternance_titres": ["alternance"],
    "hors_stack_tags": ["php"],
    "ville_dept": {"paris": "75"},
}


def _ledger(rel_path, date_email="2026-09-18T10:00:00+0200", statut="PENDING"):
    return {
        "<msg-1>": {
            "gmail_id": "gmail-1",
            "fichier": rel_path,
            "date_email": date_email,
            "fetched_at": "2026-09-18T08:00:00Z",
            "indexed_at": "",
            "statut_extraction": statut,
        }
    }


def _setup_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod, "SOURCES_DIR", tmp_path / "sources")
    monkeypatch.setattr(extract_mod, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(extract_mod, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(extract_mod, "OFFRES_CSV", tmp_path / "output" / "offres.csv")
    monkeypatch.setattr(extract_mod, "HISTORY_CSV", tmp_path / "logs" / "extraction_history.csv")


def test_main_reports_nothing_when_no_pending_files(capsys):
    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(
            extract_mod, "load_ledger", return_value=_ledger("indeed/raw.eml", statut="OK")
        ),
    ):
        main(dry_run=False)

    assert "Aucun fichier EML en attente" in capsys.readouterr().out


def test_main_marks_a_missing_file_as_erreur(tmp_path, monkeypatch, capsys):
    _setup_paths(tmp_path, monkeypatch)
    ledger = _ledger("indeed/missing.eml")

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(extract_mod, "save_ledger") as fake_save_ledger,
    ):
        main(dry_run=False)

    assert "Fichier introuvable" in capsys.readouterr().out
    saved_ledger = fake_save_ledger.call_args[0][1]
    assert saved_ledger["<msg-1>"]["statut_extraction"] == "ERREUR"


def test_main_marks_an_unreadable_file_as_erreur(tmp_path, monkeypatch, capsys):
    _setup_paths(tmp_path, monkeypatch)
    unreadable = tmp_path / "sources" / "indeed" / "raw.eml"
    unreadable.mkdir(parents=True)
    ledger = _ledger("indeed/raw.eml")

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(extract_mod, "save_ledger") as fake_save_ledger,
    ):
        main(dry_run=False)

    assert "Impossible de lire" in capsys.readouterr().out
    saved_ledger = fake_save_ledger.call_args[0][1]
    assert saved_ledger["<msg-1>"]["statut_extraction"] == "ERREUR"


def test_main_marks_unknown_provider_as_erreur(tmp_path, monkeypatch, capsys):
    sources_dir = tmp_path / "sources"
    _setup_paths(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    ledger = _ledger("indeed/raw.eml")

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(extract_mod, "detect_provider", return_value=(None, None)),
        patch.object(extract_mod, "save_ledger") as fake_save_ledger,
    ):
        main(dry_run=False)

    assert "Provider inconnu" in capsys.readouterr().out
    saved_ledger = fake_save_ledger.call_args[0][1]
    assert saved_ledger["<msg-1>"]["statut_extraction"] == "ERREUR"


def test_main_marks_a_skip_provider_as_ignore(tmp_path, monkeypatch, capsys):
    sources_dir = tmp_path / "sources"
    _setup_paths(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    ledger = _ledger("indeed/raw.eml")

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(
            extract_mod, "detect_provider", return_value=("test_provider", {"skip": True})
        ),
        patch.object(extract_mod, "save_ledger") as fake_save_ledger,
    ):
        main(dry_run=False)

    assert "EML ignoré" in capsys.readouterr().out
    saved_ledger = fake_save_ledger.call_args[0][1]
    assert saved_ledger["<msg-1>"]["statut_extraction"] == "IGNORE"


def test_main_marks_a_provider_with_no_extractor_as_ignore(tmp_path, monkeypatch, capsys):
    sources_dir = tmp_path / "sources"
    _setup_paths(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    ledger = _ledger("indeed/raw.eml")

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(extract_mod, "detect_provider", return_value=("test_provider", {})),
        patch.object(extract_mod, "EXTRACTORS", {}),
        patch.object(extract_mod, "save_ledger") as fake_save_ledger,
    ):
        main(dry_run=False)

    assert "pas d'extracteur" in capsys.readouterr().out
    saved_ledger = fake_save_ledger.call_args[0][1]
    assert saved_ledger["<msg-1>"]["statut_extraction"] == "IGNORE"


def test_main_marks_extraction_exception_as_erreur(tmp_path, monkeypatch, capsys):
    sources_dir = tmp_path / "sources"
    _setup_paths(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    ledger = _ledger("indeed/raw.eml")

    def _boom(html, msg, cfg):
        raise ValueError("boom")

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(extract_mod, "detect_provider", return_value=("test_provider", {})),
        patch.object(extract_mod, "EXTRACTORS", {"test_provider": _boom}),
        patch.object(extract_mod, "save_ledger") as fake_save_ledger,
    ):
        main(dry_run=False)

    assert "Erreur d'extraction" in capsys.readouterr().out
    saved_ledger = fake_save_ledger.call_args[0][1]
    assert saved_ledger["<msg-1>"]["statut_extraction"] == "ERREUR"


def test_main_marks_no_offers_extracted_as_partiel(tmp_path, monkeypatch, capsys):
    sources_dir = tmp_path / "sources"
    _setup_paths(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    ledger = _ledger("indeed/raw.eml")

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(extract_mod, "detect_provider", return_value=("test_provider", {})),
        patch.object(extract_mod, "EXTRACTORS", {"test_provider": lambda html, msg, cfg: []}),
        patch.object(extract_mod, "save_ledger") as fake_save_ledger,
    ):
        main(dry_run=False)

    assert "Aucune offre extraite" in capsys.readouterr().out
    saved_ledger = fake_save_ledger.call_args[0][1]
    assert saved_ledger["<msg-1>"]["statut_extraction"] == "PARTIEL"


def test_main_ignores_an_offer_with_an_empty_titre(tmp_path, monkeypatch, capsys):
    sources_dir = tmp_path / "sources"
    _setup_paths(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    ledger = _ledger("indeed/raw.eml")
    offers = [{"titre": "", "entreprise": "Acme"}]

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(extract_mod, "detect_provider", return_value=("test_provider", {})),
        patch.object(extract_mod, "EXTRACTORS", {"test_provider": lambda html, msg, cfg: offers}),
        patch.object(extract_mod, "save_ledger") as fake_save_ledger,
    ):
        main(dry_run=False)

    out = capsys.readouterr().out
    assert "Offre ignorée (titre vide)" in out
    saved_ledger = fake_save_ledger.call_args[0][1]
    assert saved_ledger["<msg-1>"]["statut_extraction"] == "PARTIEL"


def test_main_writes_a_new_offer_and_marks_the_file_ok(tmp_path, monkeypatch, capsys):
    sources_dir = tmp_path / "sources"
    _setup_paths(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    ledger = _ledger("indeed/raw.eml")
    offers = [
        {
            "titre": "Développeur Python",
            "entreprise": "Acme",
            "ville": "Paris",
            "url": "https://example.com/offre",
        }
    ]

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(extract_mod, "detect_provider", return_value=("test_provider", {})),
        patch.object(extract_mod, "EXTRACTORS", {"test_provider": lambda html, msg, cfg: offers}),
        patch.object(extract_mod, "save_ledger") as fake_save_ledger,
    ):
        main(dry_run=False)

    out = capsys.readouterr().out
    assert "1 offre(s) écrites" in out

    import_files = list((tmp_path / "output").glob("import_*.csv"))
    assert len(import_files) == 1
    rows = list(csv.DictReader(import_files[0].open(encoding="utf-8"), delimiter=";"))
    assert len(rows) == 1
    assert rows[0]["Titre"] == "Développeur Python"
    assert rows[0]["Dept"] == "75"
    assert rows[0]["Stack"] == "python"

    saved_ledger = fake_save_ledger.call_args[0][1]
    assert saved_ledger["<msg-1>"]["statut_extraction"] == "OK"

    history_rows = list(
        csv.DictReader(
            (tmp_path / "logs" / "extraction_history.csv").open(encoding="utf-8"), delimiter=";"
        )
    )
    assert len(history_rows) == 1


def test_main_marks_a_blacklisted_offer_and_sets_raison_exclusion(tmp_path, monkeypatch):
    sources_dir = tmp_path / "sources"
    _setup_paths(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    ledger = _ledger("indeed/raw.eml")
    offers = [{"titre": "Stage développeur", "entreprise": "Acme", "ville": "Paris"}]

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(extract_mod, "detect_provider", return_value=("test_provider", {})),
        patch.object(extract_mod, "EXTRACTORS", {"test_provider": lambda html, msg, cfg: offers}),
        patch.object(extract_mod, "save_ledger"),
    ):
        main(dry_run=False)

    import_file = next((tmp_path / "output").glob("import_*.csv"))
    rows = list(csv.DictReader(import_file.open(encoding="utf-8"), delimiter=";"))
    assert rows[0]["Raison_exclusion"] == "Hors profil"
    assert "Blacklisté" in rows[0]["Notes"]


def test_main_marks_a_stage_alternance_offer(tmp_path, monkeypatch):
    sources_dir = tmp_path / "sources"
    _setup_paths(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    ledger = _ledger("indeed/raw.eml")
    offers = [{"titre": "Alternance développeur", "entreprise": "Acme", "ville": "Paris"}]

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(extract_mod, "detect_provider", return_value=("test_provider", {})),
        patch.object(extract_mod, "EXTRACTORS", {"test_provider": lambda html, msg, cfg: offers}),
        patch.object(extract_mod, "save_ledger"),
    ):
        main(dry_run=False)

    import_file = next((tmp_path / "output").glob("import_*.csv"))
    rows = list(csv.DictReader(import_file.open(encoding="utf-8"), delimiter=";"))
    assert rows[0]["Raison_exclusion"] == "Stage/Alternance"


def test_main_marks_a_hors_stack_offer(tmp_path, monkeypatch):
    sources_dir = tmp_path / "sources"
    _setup_paths(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    ledger = _ledger("indeed/raw.eml")
    offers = [{"titre": "Développeur PHP", "entreprise": "Acme", "ville": "Paris"}]

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(extract_mod, "detect_provider", return_value=("test_provider", {})),
        patch.object(extract_mod, "EXTRACTORS", {"test_provider": lambda html, msg, cfg: offers}),
        patch.object(extract_mod, "save_ledger"),
    ):
        main(dry_run=False)

    import_file = next((tmp_path / "output").glob("import_*.csv"))
    rows = list(csv.DictReader(import_file.open(encoding="utf-8"), delimiter=";"))
    assert rows[0]["Raison_exclusion"] == "Hors stack"


def test_main_detects_a_doublon_via_the_dedup_map(tmp_path, monkeypatch):
    sources_dir = tmp_path / "sources"
    _setup_paths(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    ledger = _ledger("indeed/raw.eml")
    offers = [{"titre": "Développeur Python", "entreprise": "Acme", "ville": "Paris"}]

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(extract_mod, "detect_provider", return_value=("test_provider", {})),
        patch.object(extract_mod, "EXTRACTORS", {"test_provider": lambda html, msg, cfg: offers}),
        patch.object(
            extract_mod,
            "load_dedup_map",
            return_value=({"acme|paris|developpeurpython": "E000001"}, 1),
        ),
        patch.object(extract_mod, "save_ledger"),
    ):
        main(dry_run=False)

    import_file = next((tmp_path / "output").glob("import_*.csv"))
    rows = list(csv.DictReader(import_file.open(encoding="utf-8"), delimiter=";"))
    assert rows[0]["Doublon_ID"] == "E000001"


def test_main_dry_run_does_not_write_offres_ledger_or_history(tmp_path, monkeypatch, capsys):
    sources_dir = tmp_path / "sources"
    _setup_paths(tmp_path, monkeypatch)
    _write_eml(sources_dir / "indeed" / "raw.eml")
    ledger = _ledger("indeed/raw.eml")
    offers = [{"titre": "Développeur Python", "entreprise": "Acme", "ville": "Paris"}]

    with (
        patch.object(extract_mod, "load_config", return_value=CONFIG),
        patch.object(extract_mod, "load_patterns", return_value={}),
        patch.object(extract_mod, "load_ledger", return_value=ledger),
        patch.object(extract_mod, "detect_provider", return_value=("test_provider", {})),
        patch.object(extract_mod, "EXTRACTORS", {"test_provider": lambda html, msg, cfg: offers}),
        patch.object(extract_mod, "save_ledger") as fake_save_ledger,
    ):
        main(dry_run=True)

    assert list((tmp_path / "output").glob("import_*.csv")) == []
    assert not (tmp_path / "logs" / "extraction_history.csv").exists()
    fake_save_ledger.assert_not_called()
    assert "1 offre(s) simulées" in capsys.readouterr().out
