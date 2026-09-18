import csv
from datetime import datetime
from pathlib import Path

from extract.io import (
    append_history,
    append_offres,
    ensure_offres_csv,
    load_dedup_map,
    write_run_log,
)

HEADERS = ["ID", "Cle_dedup", "Titre"]


def _write_offres_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def test_load_dedup_map_returns_empty_when_the_file_does_not_exist(tmp_path):
    assert load_dedup_map(tmp_path / "offres.csv") == ({}, 0)


def test_load_dedup_map_builds_the_cle_dedup_to_id_mapping(tmp_path):
    csv_path = tmp_path / "offres.csv"
    _write_offres_csv(
        csv_path,
        [
            {"ID": "E000001", "Cle_dedup": "acme|paris|devweb", "Titre": "Dev"},
            {"ID": "E000002", "Cle_dedup": "acme|lyon|devweb", "Titre": "Dev"},
        ],
    )

    dedup, max_e = load_dedup_map(csv_path)

    assert dedup == {"acme|paris|devweb": "E000001", "acme|lyon|devweb": "E000002"}
    assert max_e == 2


def test_load_dedup_map_ignores_rows_with_an_empty_cle_dedup(tmp_path):
    csv_path = tmp_path / "offres.csv"
    _write_offres_csv(csv_path, [{"ID": "E000001", "Cle_dedup": "", "Titre": "Dev"}])

    dedup, max_e = load_dedup_map(csv_path)

    assert dedup == {}
    assert max_e == 1


def test_load_dedup_map_ignores_an_id_that_does_not_parse_as_a_number(tmp_path):
    csv_path = tmp_path / "offres.csv"
    _write_offres_csv(csv_path, [{"ID": "Exyz", "Cle_dedup": "acme|paris|devweb", "Titre": "Dev"}])

    dedup, max_e = load_dedup_map(csv_path)

    assert max_e == 0


def test_ensure_offres_csv_creates_the_offres_file_with_headers_when_missing(tmp_path):
    offres_csv = tmp_path / "offres.csv"

    ensure_offres_csv(offres_csv, None, HEADERS, write_import_headers=True)

    assert offres_csv.exists()
    with offres_csv.open(encoding="utf-8") as f:
        assert next(csv.reader(f, delimiter=";")) == HEADERS


def test_ensure_offres_csv_does_not_overwrite_an_existing_offres_file(tmp_path):
    offres_csv = tmp_path / "offres.csv"
    offres_csv.write_text("existing content", encoding="utf-8")

    ensure_offres_csv(offres_csv, None, HEADERS, write_import_headers=True)

    assert offres_csv.read_text(encoding="utf-8") == "existing content"


def test_ensure_offres_csv_creates_the_import_file_with_headers_when_requested(tmp_path):
    offres_csv = tmp_path / "offres.csv"
    import_csv = tmp_path / "import.csv"

    ensure_offres_csv(offres_csv, import_csv, HEADERS, write_import_headers=True)

    with import_csv.open(encoding="utf-8") as f:
        assert next(csv.reader(f, delimiter=";")) == HEADERS


def test_ensure_offres_csv_creates_an_empty_import_file_when_headers_not_requested(tmp_path):
    offres_csv = tmp_path / "offres.csv"
    import_csv = tmp_path / "import.csv"

    ensure_offres_csv(offres_csv, import_csv, HEADERS, write_import_headers=False)

    assert import_csv.read_text(encoding="utf-8") == ""


def test_ensure_offres_csv_skips_the_import_file_entirely_when_none(tmp_path):
    offres_csv = tmp_path / "offres.csv"

    ensure_offres_csv(offres_csv, None, HEADERS, write_import_headers=True)

    assert list(tmp_path.iterdir()) == [offres_csv]


def test_append_offres_appends_rows_to_both_the_offres_and_import_files(tmp_path):
    offres_csv = tmp_path / "offres.csv"
    import_csv = tmp_path / "import.csv"
    offres_csv.write_text("", encoding="utf-8")
    import_csv.write_text("", encoding="utf-8")
    rows = [{"ID": "E000001", "Cle_dedup": "acme|paris|devweb", "Titre": "Dev", "Extra": "ignored"}]

    append_offres(offres_csv, import_csv, rows, HEADERS)

    with offres_csv.open(encoding="utf-8") as f:
        assert list(csv.reader(f, delimiter=";"))[0] == ["E000001", "acme|paris|devweb", "Dev"]
    with import_csv.open(encoding="utf-8") as f:
        assert list(csv.reader(f, delimiter=";"))[0] == ["E000001", "acme|paris|devweb", "Dev"]


def test_append_offres_skips_the_import_file_when_none(tmp_path):
    offres_csv = tmp_path / "offres.csv"
    offres_csv.write_text("", encoding="utf-8")
    rows = [{"ID": "E000001", "Cle_dedup": "acme|paris|devweb", "Titre": "Dev"}]

    append_offres(offres_csv, None, rows, HEADERS)

    with offres_csv.open(encoding="utf-8") as f:
        assert list(csv.reader(f, delimiter=";"))[0] == ["E000001", "acme|paris|devweb", "Dev"]


def test_write_run_log_writes_the_header_entries_and_summary(tmp_path):
    log_path = tmp_path / "run.log"
    run_dt = datetime(2026, 9, 18, 10, 30, 0)

    write_run_log(log_path, run_dt, ["entry one", "entry two"], {"offres_ecrites": 3})

    content = log_path.read_text(encoding="utf-8")
    assert "=== Extraction EML — 2026-09-18 10:30:00 ===" in content
    assert "entry one" in content
    assert "entry two" in content
    assert "--- RÉSUMÉ ---" in content
    assert "offres_ecrites: 3" in content


def test_append_history_writes_the_header_on_first_write(tmp_path):
    history_csv = tmp_path / "history.csv"
    run_dt = datetime(2026, 9, 18, 10, 30, 0)

    append_history(
        history_csv,
        run_dt,
        {
            "fichiers_ok": 5,
            "offres_ecrites": 3,
            "doublons": 1,
            "ignores": 0,
            "erreurs": 0,
            "dry_run": False,
        },
    )

    rows = list(csv.DictReader(history_csv.open(encoding="utf-8"), delimiter=";"))
    assert len(rows) == 1
    assert rows[0]["Date_run"] == "2026-09-18T10:30:00"
    assert rows[0]["Fichiers_traites"] == "5"


def test_append_history_does_not_repeat_the_header_on_a_second_write(tmp_path):
    history_csv = tmp_path / "history.csv"
    run_dt = datetime(2026, 9, 18, 10, 30, 0)

    append_history(history_csv, run_dt, {})
    append_history(history_csv, run_dt, {})

    rows = list(csv.DictReader(history_csv.open(encoding="utf-8"), delimiter=";"))
    assert len(rows) == 2
