from unittest.mock import MagicMock, patch

import clear_obsolete_doublon_id as clear_mod
from clear_obsolete_doublon_id import apply_clear, main, rows_to_clear, run


def test_rows_to_clear_flags_a_doublon_id_whose_referenced_row_has_a_different_cle_dedup():
    ids = ["E000025", "E000046"]
    cles = ["E000025|ollioules|negociateurimmobilie", "E000046|solliespont|negociateurimmobilie"]
    doublon_ids = ["", "E000025"]

    assert rows_to_clear(ids, cles, doublon_ids, start_row=2) == [3]


def test_rows_to_clear_skips_rows_with_no_doublon_id():
    ids = ["E000001", "E000002"]
    cles = ["acme|paris|devweb", "acme|paris|devweb"]
    doublon_ids = ["", ""]

    assert rows_to_clear(ids, cles, doublon_ids, start_row=2) == []


def test_rows_to_clear_keeps_a_doublon_id_whose_cle_dedup_still_matches():
    ids = ["E000001", "E000002"]
    cles = ["acme|paris|devweb", "acme|paris|devweb"]
    doublon_ids = ["", "E000001"]

    assert rows_to_clear(ids, cles, doublon_ids, start_row=2) == []


def test_rows_to_clear_flags_a_doublon_id_pointing_to_an_unknown_row():
    ids = ["E000002"]
    cles = ["acme|paris|devweb"]
    doublon_ids = ["E000999"]

    assert rows_to_clear(ids, cles, doublon_ids, start_row=2) == [2]


def test_apply_clear_bundles_every_row_into_one_batch_update():
    service = MagicMock()

    apply_clear(service, "sheet-id", "OffresTest", rows=[47, 8149])

    service.spreadsheets.return_value.values.return_value.batchUpdate.assert_called_once_with(
        spreadsheetId="sheet-id",
        body={
            "valueInputOption": "RAW",
            "data": [
                {"range": "OffresTest!H47", "values": [[""]]},
                {"range": "OffresTest!H8149", "values": [[""]]},
            ],
        },
    )


def _fake_service(id_values, cle_values, doublon_id_values):
    service = MagicMock()

    def fake_get(**kwargs):
        result = MagicMock()
        range_ = kwargs["range"]
        if range_.startswith("OffresTest!A"):
            values = id_values
        elif range_.startswith("OffresTest!G"):
            values = cle_values
        else:
            values = doublon_id_values
        result.execute.return_value = {"values": [[v] if v else [] for v in values]}
        return result

    service.spreadsheets.return_value.values.return_value.get.side_effect = fake_get
    return service


def _fake_config():
    return {"sheets_sync": {"spreadsheet_id": "sheet-id"}}


def test_run_reports_nothing_to_fix_and_does_not_write(capsys):
    fake_service = _fake_service(["E000001"], ["acme|paris|devweb"], [""])
    with (
        patch.object(clear_mod, "load_config", return_value=_fake_config()),
        patch.object(clear_mod, "get_sheets_service", return_value=fake_service),
    ):
        run("OffresTest", apply=False)

    assert "Aucune ligne" in capsys.readouterr().out
    fake_service.spreadsheets.return_value.values.return_value.batchUpdate.assert_not_called()


def test_run_dry_run_reports_fixes_without_writing(capsys):
    fake_service = _fake_service(["E000002"], ["acme|paris|devweb"], ["E000999"])
    with (
        patch.object(clear_mod, "load_config", return_value=_fake_config()),
        patch.object(clear_mod, "get_sheets_service", return_value=fake_service),
    ):
        run("OffresTest", apply=False)

    out = capsys.readouterr().out
    assert "1 ligne" in out
    assert "DRY-RUN" in out
    fake_service.spreadsheets.return_value.values.return_value.batchUpdate.assert_not_called()


def test_run_applies_fixes_when_apply_is_true(capsys):
    fake_service = _fake_service(["E000002"], ["acme|paris|devweb"], ["E000999"])
    with (
        patch.object(clear_mod, "load_config", return_value=_fake_config()),
        patch.object(clear_mod, "get_sheets_service", return_value=fake_service),
    ):
        run("OffresTest", apply=True)

    fake_service.spreadsheets.return_value.values.return_value.batchUpdate.assert_called_once()
    assert "videes" in capsys.readouterr().out


def test_main_parses_sheet_name_and_defaults_apply_to_false():
    with patch.object(clear_mod, "run") as fake_run:
        main(["OffresTest"])

    fake_run.assert_called_once_with("OffresTest", apply=False)


def test_main_parses_the_apply_flag():
    with patch.object(clear_mod, "run") as fake_run:
        main(["OffresTest", "--apply"])

    fake_run.assert_called_once_with("OffresTest", apply=True)
