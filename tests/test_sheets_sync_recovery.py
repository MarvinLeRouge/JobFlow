import csv
import json
from unittest.mock import MagicMock, patch

import pytest

from sheets_sync_recovery import missing_id_sequences, read_local_offers, read_sheet_ids, run


def _write_offres_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ID", "Titre"], delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_read_local_offers_keys_rows_by_numeric_id(tmp_path):
    csv_path = tmp_path / "offres.csv"
    _write_offres_csv(
        csv_path,
        [{"ID": "E000001", "Titre": "Dev"}, {"ID": "E000002", "Titre": "Ops"}],
    )

    offers = read_local_offers(csv_path)

    assert offers[1]["Titre"] == "Dev"
    assert offers[2]["Titre"] == "Ops"


def test_read_local_offers_rejects_a_gap_in_the_local_archive(tmp_path):
    csv_path = tmp_path / "offres.csv"
    _write_offres_csv(
        csv_path,
        [{"ID": "E000001", "Titre": "Dev"}, {"ID": "E000003", "Titre": "Ops"}],
    )

    with pytest.raises(ValueError, match="[Dd]iscontinuit"):
        read_local_offers(csv_path)


def test_missing_id_sequences_returns_empty_when_nothing_missing():
    assert missing_id_sequences(sheet_ids={1, 2, 3}, local_max=3) == []


def test_missing_id_sequences_finds_a_single_internal_gap():
    sheet_ids = {1, 2, 6, 7}
    assert missing_id_sequences(sheet_ids, local_max=7) == [[3, 4, 5]]


def test_missing_id_sequences_finds_a_trailing_gap_when_sheet_lags_local():
    sheet_ids = {1, 2, 3}
    assert missing_id_sequences(sheet_ids, local_max=6) == [[4, 5, 6]]


def test_missing_id_sequences_finds_multiple_separate_gaps_in_order():
    sheet_ids = {1, 4, 5, 9}
    assert missing_id_sequences(sheet_ids, local_max=9) == [[2, 3], [6, 7, 8]]


def test_read_sheet_ids_returns_numeric_ids_from_column_a():
    service = MagicMock()
    values_get = service.spreadsheets.return_value.values.return_value.get
    values_get.return_value.execute.return_value = {
        "values": [["E000001"], ["E000002"], ["E000004"]]
    }

    ids = read_sheet_ids(service, "sheet-id", "Offres")

    assert ids == {1, 2, 4}


def _write_sync_config(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr("sheets_sync.CONFIG_LOCAL_FILE", tmp_path / "config.local.json")
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "offres_csv_headers": ["ID", "Traite", "Titre", "Raison_exclusion"],
                "sheets_sync": {
                    "spreadsheet_id": "sheet-id",
                    "sheet_name": "Offres",
                    "reference_sheet_name": "Références",
                    "reference_row_b": 2,
                    "reference_row_r": 3,
                },
            }
        ),
        encoding="utf-8",
    )


def _write_offres_full_csv(path, count):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["ID", "Traite", "Titre", "Raison_exclusion"], delimiter=";"
        )
        writer.writeheader()
        for i in range(1, count + 1):
            writer.writerow(
                {
                    "ID": f"E{i:06d}",
                    "Traite": "FALSE",
                    "Titre": f"Offre {i}",
                    "Raison_exclusion": "",
                }
            )


def _fake_service_with_sheet_ids(sheet_ids, last_data_row):
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [
            {
                "properties": {
                    "sheetId": 0,
                    "title": "Offres",
                    "gridProperties": {"rowCount": 1000},
                }
            },
            {"properties": {"sheetId": 99, "title": "Références"}},
        ]
    }

    def fake_values_get(**kwargs):
        rng = kwargs["range"]
        result = MagicMock()
        if rng.endswith("A2:A"):
            result.execute.return_value = {"values": [[f"E{i:06d}"] for i in sorted(sheet_ids)]}
        elif rng.endswith("A:A"):
            result.execute.return_value = {"values": [["ID"]] * last_data_row}
        else:
            result.execute.return_value = {"values": []}
        return result

    service.spreadsheets.return_value.values.return_value.get.side_effect = fake_values_get
    return service


def test_run_reports_no_gap_and_does_not_write(tmp_path, monkeypatch, capsys):
    _write_sync_config(tmp_path, monkeypatch)
    _write_offres_full_csv(tmp_path / "offres.csv", count=3)
    monkeypatch.setattr("sheets_sync_recovery.OFFRES_CSV", tmp_path / "offres.csv")

    fake_service = _fake_service_with_sheet_ids(sheet_ids={1, 2, 3}, last_data_row=4)
    with patch("sheets_sync.get_sheets_service", return_value=fake_service):
        run(dry_run=True)

    assert "Aucune discontinuit" in capsys.readouterr().out
    fake_service.spreadsheets.return_value.values.return_value.update.assert_not_called()


def test_run_dry_run_reports_gap_without_writing(tmp_path, monkeypatch, capsys):
    _write_sync_config(tmp_path, monkeypatch)
    _write_offres_full_csv(tmp_path / "offres.csv", count=5)
    monkeypatch.setattr("sheets_sync_recovery.OFFRES_CSV", tmp_path / "offres.csv")

    fake_service = _fake_service_with_sheet_ids(sheet_ids={1, 2, 3}, last_data_row=4)
    with patch("sheets_sync.get_sheets_service", return_value=fake_service):
        run(dry_run=True)

    out = capsys.readouterr().out
    assert "E000004" in out and "E000005" in out
    fake_service.spreadsheets.return_value.values.return_value.update.assert_not_called()


def test_run_writes_gap_rows_after_a_blank_separator_row(tmp_path, monkeypatch):
    _write_sync_config(tmp_path, monkeypatch)
    _write_offres_full_csv(tmp_path / "offres.csv", count=5)
    monkeypatch.setattr("sheets_sync_recovery.OFFRES_CSV", tmp_path / "offres.csv")

    fake_service = _fake_service_with_sheet_ids(sheet_ids={1, 2, 3}, last_data_row=4)
    with patch("sheets_sync.get_sheets_service", return_value=fake_service):
        run(dry_run=False)

    update_call = fake_service.spreadsheets.return_value.values.return_value.update
    _, kwargs = update_call.call_args
    assert kwargs["range"] == "Offres!A6:D7"
    assert kwargs["body"]["values"][0][0] == "E000004"
    assert kwargs["body"]["values"][1][0] == "E000005"
