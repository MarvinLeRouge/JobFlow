from unittest.mock import MagicMock

from backfill_raison_stage_alternance import apply_fill, rows_to_fill

TERMS = ["alternance", "alternant", "stage", "stagiaire"]


def test_rows_to_fill_matches_titles_with_a_term_and_empty_raison():
    titres = ["Developpeur en alternance", "Chef de projet", "Stagiaire dev web"]
    raisons = ["", "", ""]

    assert rows_to_fill(titres, raisons, TERMS, start_row=2) == [2, 4]


def test_rows_to_fill_skips_rows_with_a_nonempty_raison_even_if_title_matches():
    titres = ["Developpeur en alternance"]
    raisons = ["Hors profil"]

    assert rows_to_fill(titres, raisons, TERMS, start_row=2) == []


def test_rows_to_fill_skips_titles_without_any_term():
    titres = ["Developpeur backend", "Lead tech"]
    raisons = ["", ""]

    assert rows_to_fill(titres, raisons, TERMS, start_row=2) == []


def test_rows_to_fill_treats_a_missing_trailing_raison_value_as_empty():
    """values().get only returns rows up to the last non-blank cell - a
    title row past the end of the fetched Raison_exclusion column is still
    effectively empty and must be matched."""
    titres = ["Developpeur backend", "Alternant devops"]
    raisons = [""]

    assert rows_to_fill(titres, raisons, TERMS, start_row=2) == [3]


def test_apply_fill_bundles_every_row_into_one_batch_update():
    service = MagicMock()

    apply_fill(service, "sheet-id", "OffresTest", rows=[47, 8149])

    service.spreadsheets.return_value.values.return_value.batchUpdate.assert_called_once_with(
        spreadsheetId="sheet-id",
        body={
            "valueInputOption": "RAW",
            "data": [
                {"range": "OffresTest!R47", "values": [["Stage/Alternance"]]},
                {"range": "OffresTest!R8149", "values": [["Stage/Alternance"]]},
            ],
        },
    )
