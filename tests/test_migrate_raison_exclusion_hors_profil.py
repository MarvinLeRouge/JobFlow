from unittest.mock import MagicMock, patch

import migrate_raison_exclusion_hors_profil as migrate
from migrate_raison_exclusion_hors_profil import apply_rewrite, main, rows_to_rewrite, run


def test_rows_to_rewrite_matches_only_legacy_blacklist_marker():
    raison_values = ["Hors profil", "Blacklisté: immobilier", "", "Blacklisté: garde d'enfant"]

    assert rows_to_rewrite(raison_values, start_row=2) == [3, 5]


def test_rows_to_rewrite_returns_empty_when_nothing_matches():
    raison_values = ["Hors profil", "Hors stack", ""]

    assert rows_to_rewrite(raison_values, start_row=2) == []


def test_apply_rewrite_bundles_every_row_into_one_batch_update():
    """A migration run can touch many scattered rows - bundling them into a
    single values().batchUpdate call instead of one call per row keeps the
    number of Sheets API calls reasonable."""
    service = MagicMock()

    apply_rewrite(service, "sheet-id", "OffresTest", rows=[47, 8149])

    service.spreadsheets.return_value.values.return_value.batchUpdate.assert_called_once_with(
        spreadsheetId="sheet-id",
        body={
            "valueInputOption": "RAW",
            "data": [
                {"range": "OffresTest!R47", "values": [["Hors profil"]]},
                {"range": "OffresTest!R8149", "values": [["Hors profil"]]},
            ],
        },
    )


def _fake_service(raison_values):
    service = MagicMock()
    values_get = service.spreadsheets.return_value.values.return_value.get
    values_get.return_value.execute.return_value = {
        "values": [[v] if v else [] for v in raison_values]
    }
    return service


def _fake_config():
    return {"sheets_sync": {"spreadsheet_id": "sheet-id"}}


def test_run_reports_nothing_to_fix_and_does_not_write(capsys):
    fake_service = _fake_service(["Hors profil"])
    with (
        patch.object(migrate, "load_config", return_value=_fake_config()),
        patch.object(migrate, "get_sheets_service", return_value=fake_service),
    ):
        run("OffresTest", apply=False)

    assert "Aucune ligne" in capsys.readouterr().out
    fake_service.spreadsheets.return_value.values.return_value.batchUpdate.assert_not_called()


def test_run_dry_run_reports_fixes_without_writing(capsys):
    fake_service = _fake_service(["Blacklisté: immobilier"])
    with (
        patch.object(migrate, "load_config", return_value=_fake_config()),
        patch.object(migrate, "get_sheets_service", return_value=fake_service),
    ):
        run("OffresTest", apply=False)

    out = capsys.readouterr().out
    assert "1 ligne" in out
    assert "DRY-RUN" in out
    fake_service.spreadsheets.return_value.values.return_value.batchUpdate.assert_not_called()


def test_run_applies_fixes_when_apply_is_true(capsys):
    fake_service = _fake_service(["Blacklisté: immobilier"])
    with (
        patch.object(migrate, "load_config", return_value=_fake_config()),
        patch.object(migrate, "get_sheets_service", return_value=fake_service),
    ):
        run("OffresTest", apply=True)

    fake_service.spreadsheets.return_value.values.return_value.batchUpdate.assert_called_once()
    assert "mises a jour" in capsys.readouterr().out


def test_main_parses_sheet_name_and_defaults_apply_to_false():
    with patch.object(migrate, "run") as fake_run:
        main(["OffresTest"])

    fake_run.assert_called_once_with("OffresTest", apply=False)


def test_main_parses_the_apply_flag():
    with patch.object(migrate, "run") as fake_run:
        main(["OffresTest", "--apply"])

    fake_run.assert_called_once_with("OffresTest", apply=True)
