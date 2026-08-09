import csv
from unittest.mock import MagicMock

import pytest

from sheets_sync import (
    check_error_gate,
    clear_error_state,
    offer_id_number,
    read_error_state,
    read_import_rows,
    read_last_synced_id,
    rows_to_sync,
    write_error_state,
)


def test_offer_id_number_extracts_the_numeric_suffix():
    assert offer_id_number("E006545") == 6545


def test_offer_id_number_rejects_unexpected_format():
    with pytest.raises(ValueError):
        offer_id_number("not-an-id")


def test_read_import_rows_reads_semicolon_csv(tmp_path):
    csv_path = tmp_path / "import_20260101.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ID", "Titre"], delimiter=";")
        writer.writeheader()
        writer.writerow({"ID": "E000001", "Titre": "Dev"})

    rows = read_import_rows(csv_path)

    assert rows == [{"ID": "E000001", "Titre": "Dev"}]


def test_rows_to_sync_filters_by_id_strictly_greater(monkeypatch):
    rows = [{"ID": "E000001"}, {"ID": "E000002"}, {"ID": "E000003"}]

    result = rows_to_sync(rows, last_synced_id=1)

    assert result == [{"ID": "E000002"}, {"ID": "E000003"}]


def test_rows_to_sync_preserves_csv_order():
    rows = [{"ID": "E000005"}, {"ID": "E000002"}, {"ID": "E000003"}]

    result = rows_to_sync(rows, last_synced_id=1)

    assert result == [{"ID": "E000005"}, {"ID": "E000002"}, {"ID": "E000003"}]


def test_read_last_synced_id_returns_max_id_number():
    service = MagicMock()
    values_resource = service.spreadsheets.return_value.values.return_value
    values_resource.get.return_value.execute.return_value = {
        "values": [["E000001"], ["E000003"], ["E000002"]]
    }

    result = read_last_synced_id(service, "sheet-id", "Offres")

    assert result == 3


def test_read_last_synced_id_returns_zero_when_sheet_has_no_data_rows():
    service = MagicMock()
    values_resource = service.spreadsheets.return_value.values.return_value
    values_resource.get.return_value.execute.return_value = {}

    result = read_last_synced_id(service, "sheet-id", "Offres")

    assert result == 0


def test_write_then_read_error_state_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "sheets_sync_error.json")

    write_error_state("Sheets API quota exceeded")
    state = read_error_state()

    assert state["message"] == "Sheets API quota exceeded"
    assert "recorded_at" in state


def test_read_error_state_returns_none_when_no_error(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "sheets_sync_error.json")

    assert read_error_state() is None


def test_clear_error_state_removes_the_file(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "sheets_sync_error.json")
    write_error_state("some error")

    clear_error_state()

    assert read_error_state() is None


def test_clear_error_state_is_a_no_op_when_nothing_to_clear(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "sheets_sync_error.json")

    clear_error_state()  # must not raise


def test_check_error_gate_raises_when_error_state_exists(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "sheets_sync_error.json")
    write_error_state("Sheets API quota exceeded")

    with pytest.raises(SystemExit, match="Sheets API quota exceeded"):
        check_error_gate()


def test_check_error_gate_passes_silently_when_no_error(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "sheets_sync_error.json")

    check_error_gate()  # must not raise
