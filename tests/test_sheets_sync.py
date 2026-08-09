import csv
import json
from unittest.mock import MagicMock, patch

import pytest

from sheets_sync import (
    check_error_gate,
    clear_data_validation,
    clear_error_state,
    copy_reference_formatting,
    ensure_sheet_rows,
    get_last_data_row,
    get_sheet_id,
    latest_import_csv,
    offer_id_number,
    read_error_state,
    read_import_rows,
    read_last_synced_id,
    row_values,
    rows_needing_r_clear,
    rows_needing_r_dropdown,
    rows_to_sync,
    run,
    write_error_state,
    write_new_rows,
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


def test_row_values_orders_by_headers_and_injects_traite_formula():
    row = {"ID": "E000001", "Titre": "Dev", "Traite": "FALSE", "Raison_exclusion": ""}
    headers = ["ID", "Titre", "Traite", "Raison_exclusion"]

    result = row_values(row, headers, row_number=100)

    assert result == ["E000001", "Dev", '=R100<>""', ""]


def test_row_values_defaults_missing_fields_to_empty_string():
    row = {"ID": "E000001", "Traite": "FALSE"}
    headers = ["ID", "Traite", "Message_ID"]

    result = row_values(row, headers, row_number=50)

    assert result == ["E000001", '=R50<>""', ""]


def test_row_values_preserves_raison_exclusion_value():
    row = {"ID": "E000002", "Traite": "FALSE", "Raison_exclusion": "Blacklisté: nounou"}
    headers = ["ID", "Traite", "Raison_exclusion"]

    result = row_values(row, headers, row_number=200)

    assert result == ["E000002", '=R200<>""', "Blacklisté: nounou"]


def test_get_sheet_id_finds_matching_title():
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [
            {"properties": {"sheetId": 0, "title": "Offres"}},
            {"properties": {"sheetId": 558063207, "title": "Références"}},
        ]
    }

    assert get_sheet_id(service, "sheet-id", "Références") == 558063207


def test_get_sheet_id_raises_when_not_found():
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"sheetId": 0, "title": "Offres"}}]
    }

    with pytest.raises(ValueError):
        get_sheet_id(service, "sheet-id", "Nonexistent")


def test_get_last_data_row_counts_column_a_values():
    service = MagicMock()
    values_resource = service.spreadsheets.return_value.values.return_value
    values_resource.get.return_value.execute.return_value = {
        "values": [["ID"], ["E000001"], ["E000002"]]
    }

    assert get_last_data_row(service, "sheet-id", "Offres") == 3


def test_get_last_data_row_returns_one_for_header_only_sheet():
    service = MagicMock()
    values_resource = service.spreadsheets.return_value.values.return_value
    values_resource.get.return_value.execute.return_value = {"values": [["ID"]]}

    assert get_last_data_row(service, "sheet-id", "Offres") == 1


def test_ensure_sheet_rows_does_nothing_when_grid_already_big_enough():
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"sheetId": 0, "gridProperties": {"rowCount": 6000}}}]
    }

    ensure_sheet_rows(service, "sheet-id", sheet_id=0, needed_row_count=5278)

    service.spreadsheets.return_value.batchUpdate.assert_not_called()


def test_ensure_sheet_rows_extends_grid_when_too_small():
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"sheetId": 0, "gridProperties": {"rowCount": 5276}}}]
    }

    ensure_sheet_rows(service, "sheet-id", sheet_id=0, needed_row_count=5278)

    service.spreadsheets.return_value.batchUpdate.assert_called_once_with(
        spreadsheetId="sheet-id",
        body={"requests": [{"appendDimension": {"sheetId": 0, "dimension": "ROWS", "length": 2}}]},
    )


def test_copy_reference_formatting_builds_correct_copypaste_request():
    service = MagicMock()

    copy_reference_formatting(
        service,
        "sheet-id",
        sheet_id=0,
        reference_sheet_id=558063207,
        reference_row=2,
        column_index=1,
        start_row=5277,
        end_row=5279,
    )

    service.spreadsheets.return_value.batchUpdate.assert_called_once_with(
        spreadsheetId="sheet-id",
        body={
            "requests": [
                {
                    "copyPaste": {
                        "source": {
                            "sheetId": 558063207,
                            "startRowIndex": 1,
                            "endRowIndex": 2,
                            "startColumnIndex": 1,
                            "endColumnIndex": 2,
                        },
                        "destination": {
                            "sheetId": 0,
                            "startRowIndex": 5276,
                            "endRowIndex": 5279,
                            "startColumnIndex": 1,
                            "endColumnIndex": 2,
                        },
                        "pasteType": "PASTE_NORMAL",
                    }
                }
            ]
        },
    )


def test_copy_reference_formatting_targets_the_given_column():
    service = MagicMock()

    copy_reference_formatting(
        service,
        "sheet-id",
        sheet_id=0,
        reference_sheet_id=558063207,
        reference_row=3,
        column_index=17,
        start_row=5277,
        end_row=5279,
    )

    body = service.spreadsheets.return_value.batchUpdate.call_args.kwargs["body"]
    request = body["requests"][0]["copyPaste"]
    assert request["destination"]["startColumnIndex"] == 17
    assert request["destination"]["endColumnIndex"] == 18


def test_rows_needing_r_dropdown_includes_rows_with_empty_raison():
    rows = [{"Raison_exclusion": ""}, {"Raison_exclusion": ""}]

    assert rows_needing_r_dropdown(rows, start_row=100) == [(100, 101)]


def test_rows_needing_r_dropdown_excludes_rows_with_a_value():
    rows = [{"Raison_exclusion": "Blacklisté: test"}, {"Raison_exclusion": "Blacklisté: test2"}]

    assert rows_needing_r_dropdown(rows, start_row=100) == []


def test_rows_needing_r_dropdown_splits_into_contiguous_ranges():
    rows = [
        {"Raison_exclusion": ""},
        {"Raison_exclusion": "Blacklisté: x"},
        {"Raison_exclusion": ""},
        {"Raison_exclusion": ""},
        {"Raison_exclusion": "Blacklisté: y"},
    ]

    assert rows_needing_r_dropdown(rows, start_row=100) == [(100, 100), (102, 103)]


def test_rows_needing_r_dropdown_handles_missing_key_as_empty():
    rows = [{}]

    assert rows_needing_r_dropdown(rows, start_row=100) == [(100, 100)]


def test_rows_needing_r_clear_includes_rows_with_a_value():
    rows = [{"Raison_exclusion": "Blacklisté: test"}, {"Raison_exclusion": "Blacklisté: test2"}]

    assert rows_needing_r_clear(rows, start_row=100) == [(100, 101)]


def test_rows_needing_r_clear_excludes_rows_with_empty_raison():
    rows = [{"Raison_exclusion": ""}, {"Raison_exclusion": ""}]

    assert rows_needing_r_clear(rows, start_row=100) == []


def test_rows_needing_r_clear_splits_into_contiguous_ranges():
    rows = [
        {"Raison_exclusion": "Blacklisté: x"},
        {"Raison_exclusion": ""},
        {"Raison_exclusion": "Blacklisté: y"},
        {"Raison_exclusion": "Blacklisté: z"},
        {"Raison_exclusion": ""},
    ]

    assert rows_needing_r_clear(rows, start_row=100) == [(100, 100), (102, 103)]


def test_clear_data_validation_builds_correct_request():
    service = MagicMock()

    clear_data_validation(
        service, "sheet-id", sheet_id=0, column_index=17, start_row=5280, end_row=5280
    )

    service.spreadsheets.return_value.batchUpdate.assert_called_once_with(
        spreadsheetId="sheet-id",
        body={
            "requests": [
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": 5279,
                            "endRowIndex": 5280,
                            "startColumnIndex": 17,
                            "endColumnIndex": 18,
                        },
                    }
                }
            ]
        },
    )


def test_write_new_rows_calls_values_update_with_correct_range_and_formula():
    service = MagicMock()
    headers = ["ID", "Traite"]
    rows = [
        {"ID": "E000010", "Traite": "FALSE"},
        {"ID": "E000011", "Traite": "FALSE"},
    ]

    write_new_rows(service, "sheet-id", "Offres", rows, headers, start_row=100)

    values_resource = service.spreadsheets.return_value.values.return_value
    values_resource.update.assert_called_once_with(
        spreadsheetId="sheet-id",
        range="Offres!A100:B101",
        valueInputOption="USER_ENTERED",
        body={
            "values": [
                ["E000010", '=R100<>""'],
                ["E000011", '=R101<>""'],
            ]
        },
    )


def test_write_new_rows_does_nothing_for_empty_list():
    service = MagicMock()

    write_new_rows(service, "sheet-id", "Offres", [], ["ID"], start_row=100)

    service.spreadsheets.return_value.values.return_value.update.assert_not_called()


def test_latest_import_csv_returns_path_when_file_exists(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.OUTPUT_DIR", tmp_path)
    (tmp_path / "import_20260101.csv").write_text("", encoding="utf-8")

    assert latest_import_csv(today="20260101") == tmp_path / "import_20260101.csv"


def test_latest_import_csv_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.OUTPUT_DIR", tmp_path)

    assert latest_import_csv(today="20260101") is None


def _write_sync_config(tmp_path, monkeypatch):
    monkeypatch.setattr("sheets_sync.ERROR_STATE_FILE", tmp_path / "error.json")
    monkeypatch.setattr("sheets_sync.OUTPUT_DIR", tmp_path)
    monkeypatch.setattr("sheets_sync.CONFIG_FILE", tmp_path / "config.json")
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "offres_csv_headers": ["ID", "Traite", "Raison_exclusion"],
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


def _write_import_csv(tmp_path, today: str) -> None:
    import_path = tmp_path / f"import_{today}.csv"
    with import_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ID", "Traite", "Raison_exclusion"], delimiter=";")
        writer.writeheader()
        writer.writerow({"ID": "E000002", "Traite": "FALSE", "Raison_exclusion": ""})


def test_run_dry_run_does_not_write(tmp_path, monkeypatch):
    _write_sync_config(tmp_path, monkeypatch)
    _write_import_csv(tmp_path, "20260101")

    fake_service = MagicMock()
    fake_service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [
            {"properties": {"sheetId": 0, "title": "Offres"}},
            {"properties": {"sheetId": 558063207, "title": "Références"}},
        ]
    }
    values_get = fake_service.spreadsheets.return_value.values.return_value.get
    values_get.return_value.execute.return_value = {"values": [["E000001"]]}
    with patch("sheets_sync.get_sheets_service", return_value=fake_service):
        run(dry_run=True, today="20260101")

    fake_service.spreadsheets.return_value.values.return_value.update.assert_not_called()
    fake_service.spreadsheets.return_value.batchUpdate.assert_not_called()


def test_run_writes_error_state_on_exception(tmp_path, monkeypatch):
    _write_sync_config(tmp_path, monkeypatch)
    _write_import_csv(tmp_path, "20260101")

    with patch("sheets_sync.get_sheets_service", side_effect=RuntimeError("API quota exceeded")):
        with pytest.raises(RuntimeError):
            run(dry_run=False, today="20260101")

    state = read_error_state()
    assert "API quota exceeded" in state["message"]


def test_run_skips_when_no_import_csv_found(tmp_path, monkeypatch, capsys):
    _write_sync_config(tmp_path, monkeypatch)

    run(dry_run=True, today="20260101")

    assert "Aucun fichier d'import" in capsys.readouterr().out


def test_run_copies_formatting_before_writing_values(tmp_path, monkeypatch):
    """Order matters: ensure_sheet_rows must run before
    copy_reference_formatting, which itself must run before write_new_rows,
    or the final values would get overwritten by the placeholder from the
    copy step instead of the other way around, and copyPaste would fail
    against a grid that hasn't been grown yet."""
    _write_sync_config(tmp_path, monkeypatch)
    _write_import_csv(tmp_path, "20260101")

    call_order = []
    fake_service = MagicMock()
    values_get = fake_service.spreadsheets.return_value.values.return_value.get
    values_get.return_value.execute.return_value = {"values": []}
    fake_service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [
            {"properties": {"sheetId": 0, "title": "Offres"}},
            {"properties": {"sheetId": 558063207, "title": "Références"}},
        ]
    }

    def record_ensure_sheet_rows(*args, **kwargs):
        call_order.append("ensure_sheet_rows")

    def record_batch_update(**kwargs):
        call_order.append("copy_reference_formatting")
        return MagicMock()

    def record_values_update(**kwargs):
        call_order.append("write_new_rows")
        return MagicMock()

    fake_service.spreadsheets.return_value.batchUpdate.side_effect = record_batch_update
    fake_service.spreadsheets.return_value.values.return_value.update.side_effect = (
        record_values_update
    )

    with (
        patch("sheets_sync.get_sheets_service", return_value=fake_service),
        patch("sheets_sync.ensure_sheet_rows", side_effect=record_ensure_sheet_rows),
    ):
        run(dry_run=False, today="20260101")

    assert call_order == [
        "ensure_sheet_rows",
        "copy_reference_formatting",
        "copy_reference_formatting",
        "write_new_rows",
    ]


def test_run_applies_r_dropdown_only_to_rows_without_a_pre_filled_reason(tmp_path, monkeypatch):
    """Row 1 has no Raison_exclusion (needs the dropdown); row 2 already has
    one from extract_eml.py's blacklist detection (must keep its plain
    value with no validation, or Sheets shows a 'not in list' warning)."""
    _write_sync_config(tmp_path, monkeypatch)
    import_path = tmp_path / "import_20260101.csv"
    with import_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ID", "Traite", "Raison_exclusion"], delimiter=";")
        writer.writeheader()
        writer.writerow({"ID": "E000002", "Traite": "FALSE", "Raison_exclusion": ""})
        writer.writerow(
            {"ID": "E000003", "Traite": "FALSE", "Raison_exclusion": "Blacklisté: test"}
        )

    fake_service = MagicMock()
    values_get = fake_service.spreadsheets.return_value.values.return_value.get
    values_get.return_value.execute.return_value = {"values": []}
    fake_service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [
            {"properties": {"sheetId": 0, "title": "Offres"}},
            {"properties": {"sheetId": 558063207, "title": "Références"}},
        ]
    }

    with (
        patch("sheets_sync.get_sheets_service", return_value=fake_service),
        patch("sheets_sync.ensure_sheet_rows"),
        patch("sheets_sync.copy_reference_formatting") as fake_copy_reference_formatting,
    ):
        run(dry_run=False, today="20260101")

    r_calls = [call for call in fake_copy_reference_formatting.call_args_list if call.args[5] == 2]
    assert len(r_calls) == 1
    assert r_calls[0].args[6:] == (1, 1)


def test_run_clears_r_validation_only_on_rows_with_a_pre_filled_reason(tmp_path, monkeypatch):
    """Row 1 has no Raison_exclusion (gets the dropdown copy, no clear); row
    2 already has one from extract_eml.py's blacklist detection (gets the
    validation explicitly cleared, no dropdown copy) - newly appended rows
    can otherwise inherit a stale dropdown from the row above them."""
    _write_sync_config(tmp_path, monkeypatch)
    import_path = tmp_path / "import_20260101.csv"
    with import_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["ID", "Traite", "Raison_exclusion"], delimiter=";")
        writer.writeheader()
        writer.writerow({"ID": "E000002", "Traite": "FALSE", "Raison_exclusion": ""})
        writer.writerow(
            {"ID": "E000003", "Traite": "FALSE", "Raison_exclusion": "Blacklisté: test"}
        )

    fake_service = MagicMock()
    values_get = fake_service.spreadsheets.return_value.values.return_value.get
    values_get.return_value.execute.return_value = {"values": []}
    fake_service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [
            {"properties": {"sheetId": 0, "title": "Offres"}},
            {"properties": {"sheetId": 558063207, "title": "Références"}},
        ]
    }

    with (
        patch("sheets_sync.get_sheets_service", return_value=fake_service),
        patch("sheets_sync.ensure_sheet_rows"),
        patch("sheets_sync.copy_reference_formatting") as fake_copy_reference_formatting,
        patch("sheets_sync.clear_data_validation") as fake_clear_data_validation,
    ):
        run(dry_run=False, today="20260101")

    r_dropdown_calls = [
        call for call in fake_copy_reference_formatting.call_args_list if call.args[5] == 2
    ]
    assert len(r_dropdown_calls) == 1
    assert r_dropdown_calls[0].args[6:] == (1, 1)

    fake_clear_data_validation.assert_called_once()
    clear_call = fake_clear_data_validation.call_args
    assert clear_call.args[3] == 2
    assert clear_call.args[4:] == (2, 2)
