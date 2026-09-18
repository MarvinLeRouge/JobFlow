from unittest.mock import MagicMock, patch

import backfill_raison_hors_stack as backfill
from backfill_raison_hors_stack import apply_fill, main, read_stack_column, rows_to_fill, run

EXCLUDED_TAGS = ["C++", "C#", ".Net", "Java"]


def test_rows_to_fill_matches_stacks_with_an_excluded_tag_and_empty_raison():
    stacks = ["C++,Linux", "Python,Django", "Java,Spring"]
    raisons = ["", "", ""]

    assert rows_to_fill(stacks, raisons, EXCLUDED_TAGS, start_row=2) == [2, 4]


def test_rows_to_fill_skips_rows_with_a_nonempty_raison_even_if_stack_matches():
    stacks = ["Java,Spring"]
    raisons = ["Hors profil"]

    assert rows_to_fill(stacks, raisons, EXCLUDED_TAGS, start_row=2) == []


def test_rows_to_fill_skips_stacks_without_any_excluded_tag():
    stacks = ["Python,Django", "PHP,Symfony"]
    raisons = ["", ""]

    assert rows_to_fill(stacks, raisons, EXCLUDED_TAGS, start_row=2) == []


def test_rows_to_fill_treats_a_missing_trailing_raison_value_as_empty():
    stacks = ["Python,Django", "Java,Spring"]
    raisons = [""]

    assert rows_to_fill(stacks, raisons, EXCLUDED_TAGS, start_row=2) == [3]


def test_apply_fill_bundles_every_row_into_one_batch_update():
    service = MagicMock()

    apply_fill(service, "sheet-id", "OffresTest", rows=[47, 8149])

    service.spreadsheets.return_value.values.return_value.batchUpdate.assert_called_once_with(
        spreadsheetId="sheet-id",
        body={
            "valueInputOption": "RAW",
            "data": [
                {"range": "OffresTest!R47", "values": [["Hors stack"]]},
                {"range": "OffresTest!R8149", "values": [["Hors stack"]]},
            ],
        },
    )


def test_read_stack_column_pads_blank_rows_with_an_empty_string():
    service = MagicMock()
    values_get = service.spreadsheets.return_value.values.return_value.get
    values_get.return_value.execute.return_value = {"values": [["Java,Spring"], []]}

    stacks = read_stack_column(service, "sheet-id", "OffresTest")

    assert stacks == ["Java,Spring", ""]
    values_get.assert_called_once_with(spreadsheetId="sheet-id", range="OffresTest!Q2:Q")


def _fake_service(stack_values, raison_values):
    service = MagicMock()

    def fake_get(**kwargs):
        result = MagicMock()
        if kwargs["range"].startswith("OffresTest!Q"):
            result.execute.return_value = {"values": [[v] if v else [] for v in stack_values]}
        else:
            result.execute.return_value = {"values": [[v] if v else [] for v in raison_values]}
        return result

    service.spreadsheets.return_value.values.return_value.get.side_effect = fake_get
    return service


def _fake_config():
    return {"sheets_sync": {"spreadsheet_id": "sheet-id"}, "hors_stack_tags": EXCLUDED_TAGS}


def test_run_reports_nothing_to_fix_and_does_not_write(capsys):
    fake_service = _fake_service(["Python,Django"], [""])
    with (
        patch.object(backfill, "load_config", return_value=_fake_config()),
        patch.object(backfill, "get_sheets_service", return_value=fake_service),
    ):
        run("OffresTest", apply=False)

    assert "Aucune ligne" in capsys.readouterr().out
    fake_service.spreadsheets.return_value.values.return_value.batchUpdate.assert_not_called()


def test_run_dry_run_reports_fixes_without_writing(capsys):
    fake_service = _fake_service(["Java,Spring"], [""])
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
    fake_service = _fake_service(["Java,Spring"], [""])
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
