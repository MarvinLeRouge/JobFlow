from unittest.mock import MagicMock, patch

import backfill_cle_dedup_row_id as backfill
from backfill_cle_dedup_row_id import (
    apply_fix,
    main,
    read_cle_dedup_column,
    read_id_column,
    rows_to_fix,
    run,
)


def test_rows_to_fix_replaces_the_inconnu_and_inconnue_placeholder_segments():
    ids = ["E000001", "E000002"]
    cles = ["inconnu|inconnue|condicionesdeuso", "acme|paris|devweb"]

    assert rows_to_fix(ids, cles, start_row=2) == [(2, "E000001|E000001|condicionesdeuso")]


def test_rows_to_fix_replaces_only_the_placeholder_segment_not_the_whole_key():
    ids = ["E000026"]
    cles = ["inconnu|ollioules|negociateurimmobilie"]

    assert rows_to_fix(ids, cles, start_row=2) == [(2, "E000026|ollioules|negociateurimmobilie")]


def test_rows_to_fix_skips_keys_with_no_placeholder_segment():
    ids = ["E000002"]
    cles = ["acme|paris|devweb"]

    assert rows_to_fix(ids, cles, start_row=2) == []


def test_rows_to_fix_does_not_match_a_substring_that_merely_contains_inconnu():
    """A real (non-placeholder) segment that happens to contain "inconnu" as
    a substring - e.g. a title slug - must not be mistaken for the exact
    placeholder token."""
    ids = ["E000003"]
    cles = ["acme|paris|posteinconnu"]

    assert rows_to_fix(ids, cles, start_row=2) == []


def test_apply_fix_bundles_every_row_into_one_batch_update():
    service = MagicMock()

    apply_fix(
        service,
        "sheet-id",
        "OffresTest",
        fixes=[(47, "E000046|E000046|devweb"), (8149, "acme|E008148|devweb")],
    )

    service.spreadsheets.return_value.values.return_value.batchUpdate.assert_called_once_with(
        spreadsheetId="sheet-id",
        body={
            "valueInputOption": "RAW",
            "data": [
                {"range": "OffresTest!G47", "values": [["E000046|E000046|devweb"]]},
                {"range": "OffresTest!G8149", "values": [["acme|E008148|devweb"]]},
            ],
        },
    )


def test_read_id_column_pads_blank_rows_with_an_empty_string():
    service = MagicMock()
    values_get = service.spreadsheets.return_value.values.return_value.get
    values_get.return_value.execute.return_value = {"values": [["E000001"], [], ["E000003"]]}

    ids = read_id_column(service, "sheet-id", "OffresTest")

    assert ids == ["E000001", "", "E000003"]
    values_get.assert_called_once_with(spreadsheetId="sheet-id", range="OffresTest!A2:A")


def test_read_cle_dedup_column_pads_blank_rows_with_an_empty_string():
    service = MagicMock()
    values_get = service.spreadsheets.return_value.values.return_value.get
    values_get.return_value.execute.return_value = {"values": [["a|b|c"], []]}

    cles = read_cle_dedup_column(service, "sheet-id", "OffresTest")

    assert cles == ["a|b|c", ""]
    values_get.assert_called_once_with(spreadsheetId="sheet-id", range="OffresTest!G2:G")


def _fake_service(id_values, cle_values):
    service = MagicMock()

    def fake_get(**kwargs):
        result = MagicMock()
        if kwargs["range"].startswith("OffresTest!A"):
            result.execute.return_value = {"values": [[v] if v else [] for v in id_values]}
        else:
            result.execute.return_value = {"values": [[v] if v else [] for v in cle_values]}
        return result

    service.spreadsheets.return_value.values.return_value.get.side_effect = fake_get
    return service


def _fake_config():
    return {"sheets_sync": {"spreadsheet_id": "sheet-id"}}


def test_run_reports_nothing_to_fix_and_does_not_write(capsys):
    fake_service = _fake_service(["E000001"], ["acme|paris|devweb"])
    with (
        patch.object(backfill, "load_config", return_value=_fake_config()),
        patch.object(backfill, "get_sheets_service", return_value=fake_service),
    ):
        run("OffresTest", apply=False)

    assert "Aucune ligne" in capsys.readouterr().out
    fake_service.spreadsheets.return_value.values.return_value.batchUpdate.assert_not_called()


def test_run_dry_run_reports_fixes_without_writing(capsys):
    fake_service = _fake_service(["E000001"], ["inconnu|paris|devweb"])
    with (
        patch.object(backfill, "load_config", return_value=_fake_config()),
        patch.object(backfill, "get_sheets_service", return_value=fake_service),
    ):
        run("OffresTest", apply=False)

    out = capsys.readouterr().out
    assert "1 ligne" in out
    assert "DRY-RUN" in out
    fake_service.spreadsheets.return_value.values.return_value.batchUpdate.assert_not_called()


def test_run_applies_fixes_when_apply_is_true(capsys):
    fake_service = _fake_service(["E000001"], ["inconnu|paris|devweb"])
    with (
        patch.object(backfill, "load_config", return_value=_fake_config()),
        patch.object(backfill, "get_sheets_service", return_value=fake_service),
    ):
        run("OffresTest", apply=True)

    fake_service.spreadsheets.return_value.values.return_value.batchUpdate.assert_called_once()
    assert "mises a jour" in capsys.readouterr().out


def test_main_parses_sheet_name_and_defaults_apply_to_false():
    with patch.object(backfill, "run") as fake_run:
        main(["OffresTest"])

    fake_run.assert_called_once_with("OffresTest", apply=False)


def test_main_parses_the_apply_flag():
    with patch.object(backfill, "run") as fake_run:
        main(["OffresTest", "--apply"])

    fake_run.assert_called_once_with("OffresTest", apply=True)
