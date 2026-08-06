import csv
from pathlib import Path

from migrate_eml_index_to_ledger import BEFORE_GMAIL_API, build_ledger_from_csv


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
