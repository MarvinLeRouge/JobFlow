from unittest.mock import MagicMock, patch

import backfill_r_dropdown as backfill
from backfill_r_dropdown import (
    apply_dropdown_validation,
    fetch_dropdown_values,
    main,
    read_raison_column,
    rows_needing_backfill,
    run,
)


def test_fetch_dropdown_values_reads_condition_values_from_the_reference_cell():
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [
            {
                "data": [
                    {
                        "rowData": [
                            {
                                "values": [
                                    {
                                        "dataValidation": {
                                            "condition": {
                                                "type": "ONE_OF_LIST",
                                                "values": [
                                                    {"userEnteredValue": "Non précisé"},
                                                    {"userEnteredValue": "Hors stack"},
                                                ],
                                            }
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    result = fetch_dropdown_values(service, "sheet-id", "Références", 3)

    assert result == ["Non précisé", "Hors stack"]
    service.spreadsheets.return_value.get.assert_called_once_with(
        spreadsheetId="sheet-id",
        ranges=["Références!B3"],
        fields="sheets.data.rowData.values.dataValidation",
        includeGridData=True,
    )


def test_read_raison_column_pads_blank_rows_as_empty_strings():
    service = MagicMock()
    values_get = service.spreadsheets.return_value.values.return_value.get
    values_get.return_value.execute.return_value = {
        "values": [["Hors stack"], [], ["Blacklisté: test"]]
    }

    result = read_raison_column(service, "sheet-id", "OffresTest")

    assert result == ["Hors stack", "", "Blacklisté: test"]
    values_get.assert_called_once_with(spreadsheetId="sheet-id", range="OffresTest!R2:R")


def test_rows_needing_backfill_includes_only_rows_with_an_exact_dropdown_value():
    valid = {"Hors stack", "Stage/Alternance"}
    raison_values = ["Hors stack", "", "Blacklisté: test", "Stage/Alternance"]

    assert rows_needing_backfill(raison_values, valid, start_row=2) == [(2, 2), (5, 5)]


def test_rows_needing_backfill_splits_into_contiguous_ranges():
    valid = {"Hors stack"}
    raison_values = ["Hors stack", "Hors stack", "", "Hors stack"]

    assert rows_needing_backfill(raison_values, valid, start_row=2) == [(2, 3), (5, 5)]


def test_rows_needing_backfill_returns_empty_when_nothing_matches():
    valid = {"Hors stack"}
    raison_values = ["", "Blacklisté: test"]

    assert rows_needing_backfill(raison_values, valid, start_row=2) == []


def test_apply_dropdown_validation_bundles_every_range_into_one_batch_update():
    """A backfill run can involve hundreds of ranges - bundling them into a
    single batchUpdate call instead of one call per range keeps the number
    of Sheets API calls reasonable. Each request copies validation only
    (PASTE_DATA_VALIDATION) from the reference cell, rather than rebuilding
    a rule through setDataValidation, which cannot carry the reference
    cell's colored-chip styling (not exposed by the Sheets API at all)."""
    service = MagicMock()

    apply_dropdown_validation(
        service,
        "sheet-id",
        sheet_id=0,
        reference_sheet_id=99,
        reference_row=3,
        column_index=17,
        ranges=[(5, 7), (10, 10)],
    )

    def copy_paste_request(start_row, end_row):
        return {
            "copyPaste": {
                "source": {
                    "sheetId": 99,
                    "startRowIndex": 2,
                    "endRowIndex": 3,
                    "startColumnIndex": 1,
                    "endColumnIndex": 2,
                },
                "destination": {
                    "sheetId": 0,
                    "startRowIndex": start_row - 1,
                    "endRowIndex": end_row,
                    "startColumnIndex": 17,
                    "endColumnIndex": 18,
                },
                "pasteType": "PASTE_DATA_VALIDATION",
            }
        }

    service.spreadsheets.return_value.batchUpdate.assert_called_once_with(
        spreadsheetId="sheet-id",
        body={
            "requests": [
                copy_paste_request(5, 7),
                copy_paste_request(10, 10),
            ]
        },
    )


def _fake_service(valid_values, raison_values):
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [
            {
                "data": [
                    {
                        "rowData": [
                            {
                                "values": [
                                    {
                                        "dataValidation": {
                                            "condition": {
                                                "values": [
                                                    {"userEnteredValue": v} for v in valid_values
                                                ]
                                            }
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    values_get = service.spreadsheets.return_value.values.return_value.get
    values_get.return_value.execute.return_value = {
        "values": [[v] if v else [] for v in raison_values]
    }
    return service


def _fake_config():
    return {
        "sheets_sync": {
            "spreadsheet_id": "sheet-id",
            "reference_sheet_name": "Références",
            "reference_row_r": 3,
        },
        "offres_csv_headers": ["ID", "Titre", "Raison_exclusion"],
    }


def test_run_reports_nothing_to_fix_and_does_not_write(capsys):
    fake_service = _fake_service(["Hors stack"], ["Blacklisté: test"])
    with (
        patch.object(backfill, "load_config", return_value=_fake_config()),
        patch.object(backfill, "get_sheets_service", return_value=fake_service),
        patch.object(backfill, "get_sheet_id", return_value=0),
    ):
        run("OffresTest", apply=False)

    assert "Aucune ligne" in capsys.readouterr().out
    fake_service.spreadsheets.return_value.batchUpdate.assert_not_called()


def test_run_dry_run_reports_fixes_without_writing(capsys):
    fake_service = _fake_service(["Hors stack"], ["Hors stack"])
    with (
        patch.object(backfill, "load_config", return_value=_fake_config()),
        patch.object(backfill, "get_sheets_service", return_value=fake_service),
        patch.object(backfill, "get_sheet_id", return_value=0),
    ):
        run("OffresTest", apply=False)

    out = capsys.readouterr().out
    assert "1 ligne(s) sur 1 plage(s)" in out
    assert "DRY-RUN" in out
    fake_service.spreadsheets.return_value.batchUpdate.assert_not_called()


def test_run_applies_fixes_when_apply_is_true(capsys):
    fake_service = _fake_service(["Hors stack"], ["Hors stack"])
    with (
        patch.object(backfill, "load_config", return_value=_fake_config()),
        patch.object(backfill, "get_sheets_service", return_value=fake_service),
        patch.object(backfill, "get_sheet_id", return_value=0),
    ):
        run("OffresTest", apply=True)

    fake_service.spreadsheets.return_value.batchUpdate.assert_called_once()
    assert "Validation appliquee" in capsys.readouterr().out


def test_main_parses_sheet_name_and_defaults_apply_to_false():
    with patch.object(backfill, "run") as fake_run:
        main(["OffresTest"])

    fake_run.assert_called_once_with("OffresTest", apply=False)


def test_main_parses_the_apply_flag():
    with patch.object(backfill, "run") as fake_run:
        main(["OffresTest", "--apply"])

    fake_run.assert_called_once_with("OffresTest", apply=True)
