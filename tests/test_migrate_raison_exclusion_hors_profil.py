from unittest.mock import MagicMock

from migrate_raison_exclusion_hors_profil import apply_rewrite, rows_to_rewrite


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
