from unittest.mock import MagicMock

from backfill_cle_dedup_row_id import apply_fix, rows_to_fix


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
