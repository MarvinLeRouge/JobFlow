from unittest.mock import MagicMock

from backfill_raison_hors_stack import apply_fill, rows_to_fill

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
