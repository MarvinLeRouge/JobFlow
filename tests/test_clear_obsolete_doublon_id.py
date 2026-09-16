from unittest.mock import MagicMock

from clear_obsolete_doublon_id import apply_clear, rows_to_clear


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
