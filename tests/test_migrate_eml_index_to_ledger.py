import csv
import json
from pathlib import Path

import pytest

import migrate_eml_index_to_ledger as migrate
from migrate_eml_index_to_ledger import BEFORE_GMAIL_API, build_ledger_from_csv, main


def _write_index_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def test_build_ledger_from_csv_maps_fields(tmp_path):
    csv_path = tmp_path / "eml_index.csv"
    _write_index_csv(
        csv_path,
        ["Message-ID", "Fichier", "Date_email", "Date_indexation", "Statut_extraction"],
        [
            {
                "Message-ID": "<msg-1>",
                "Fichier": "indeed/20260806-1032-foo.eml",
                "Date_email": "2026-08-06T10:32:00+0200",
                "Date_indexation": "2026-08-06T10:35:00Z",
                "Statut_extraction": "OK",
            }
        ],
    )

    ledger = build_ledger_from_csv(csv_path)

    assert ledger == {
        "<msg-1>": {
            "gmail_id": BEFORE_GMAIL_API,
            "fichier": "indeed/20260806-1032-foo.eml",
            "date_email": "2026-08-06T10:32:00+0200",
            "fetched_at": "2026-08-06T10:35:00Z",
            "indexed_at": "2026-08-06T10:35:00Z",
            "statut_extraction": "OK",
        }
    }


def test_build_ledger_from_csv_defaults_missing_statut_to_pending(tmp_path):
    csv_path = tmp_path / "eml_index.csv"
    _write_index_csv(
        csv_path,
        ["Message-ID", "Fichier", "Date_email", "Date_indexation"],
        [
            {
                "Message-ID": "<msg-2>",
                "Fichier": "linkedin/20260601-0900-bar.eml",
                "Date_email": "2026-06-01T09:00:00+0200",
                "Date_indexation": "2026-06-01T09:05:00Z",
            }
        ],
    )

    ledger = build_ledger_from_csv(csv_path)

    assert ledger["<msg-2>"]["statut_extraction"] == "PENDING"
    assert ledger["<msg-2>"]["gmail_id"] == BEFORE_GMAIL_API


def test_build_ledger_from_csv_missing_file_returns_empty_dict(tmp_path):
    assert build_ledger_from_csv(tmp_path / "does_not_exist.csv") == {}


def test_main_dry_run_reports_the_count_and_does_not_write(tmp_path, monkeypatch, capsys):
    index_csv = tmp_path / "eml_index.csv"
    ledger_json = tmp_path / "email_ledger.json"
    _write_index_csv(
        index_csv,
        ["Message-ID", "Fichier", "Date_email", "Date_indexation"],
        [{"Message-ID": "<msg-1>", "Fichier": "a.eml", "Date_email": "", "Date_indexation": ""}],
    )
    monkeypatch.setattr(migrate, "INDEX_CSV", index_csv)
    monkeypatch.setattr(migrate, "LEDGER_JSON", ledger_json)

    main(dry_run=True)

    out = capsys.readouterr().out
    assert "1 entrée(s)" in out
    assert "[DRY-RUN]" in out
    assert not ledger_json.exists()


def test_main_writes_the_ledger_when_not_dry_run(tmp_path, monkeypatch, capsys):
    index_csv = tmp_path / "eml_index.csv"
    ledger_json = tmp_path / "email_ledger.json"
    _write_index_csv(
        index_csv,
        ["Message-ID", "Fichier", "Date_email", "Date_indexation"],
        [{"Message-ID": "<msg-1>", "Fichier": "a.eml", "Date_email": "", "Date_indexation": ""}],
    )
    monkeypatch.setattr(migrate, "INDEX_CSV", index_csv)
    monkeypatch.setattr(migrate, "LEDGER_JSON", ledger_json)

    main(dry_run=False)

    assert "Ledger écrit" in capsys.readouterr().out
    written = json.loads(ledger_json.read_text(encoding="utf-8"))
    assert "<msg-1>" in written


def test_main_aborts_when_the_ledger_already_exists(tmp_path, monkeypatch, capsys):
    index_csv = tmp_path / "eml_index.csv"
    ledger_json = tmp_path / "email_ledger.json"
    _write_index_csv(index_csv, ["Message-ID"], [{"Message-ID": "<msg-1>"}])
    ledger_json.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(migrate, "INDEX_CSV", index_csv)
    monkeypatch.setattr(migrate, "LEDGER_JSON", ledger_json)

    with pytest.raises(SystemExit):
        main(dry_run=False)

    assert "existe déjà" in capsys.readouterr().out
