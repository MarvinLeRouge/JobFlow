from unittest.mock import MagicMock, patch

import consolidate_conditional_format_rules as consolidate_module
from consolidate_conditional_format_rules import (
    build_requests,
    consolidate,
    find_b_and_r_only_rules,
    main,
    run,
)


def _rule(ranges: list[tuple[int, int, int, int]]) -> dict:
    return {
        "ranges": [
            {
                "startRowIndex": s,
                "endRowIndex": e,
                "startColumnIndex": c0,
                "endColumnIndex": c1,
            }
            for s, e, c0, c1 in ranges
        ],
    }


def test_find_b_and_r_only_rules_matches_a_rule_scoped_to_exactly_columns_b_and_r():
    """Historical copy-paste artifact: a per-cell rule dragged in from the
    origin cell's formatting, scoped to only columns B and R - redundant
    with the equivalent whole-row rule that already colors the same range."""
    rules = [
        _rule([(99, 200, 1, 2), (99, 200, 17, 18)]),
        _rule([(1, 8157, 0, 26)]),
    ]

    assert find_b_and_r_only_rules(rules) == [0]


def test_find_b_and_r_only_rules_matches_every_instance_not_just_duplicates():
    """Unlike a duplicate-grouping approach, a single B+R-scoped rule with
    no sibling is just as redundant as fifty near-identical ones and must
    still be flagged."""
    rules = [_rule([(99, 200, 1, 2), (99, 200, 17, 18)])]

    assert find_b_and_r_only_rules(rules) == [0]


def test_find_b_and_r_only_rules_ignores_rules_scoped_to_other_columns():
    rules = [
        _rule([(1, 8157, 0, 1)]),
        _rule([(0, 1, 0, 26)]),
    ]

    assert find_b_and_r_only_rules(rules) == []


def test_find_b_and_r_only_rules_ignores_a_rule_whose_ranges_cover_more_than_b_and_r():
    rules = [_rule([(99, 200, 1, 2), (99, 200, 17, 18), (99, 200, 5, 6)])]

    assert find_b_and_r_only_rules(rules) == []


def test_build_requests_deletes_every_matched_index_in_descending_order():
    requests = build_requests(sheet_id=42, indices=[2, 5, 9])

    assert requests == [
        {"deleteConditionalFormatRule": {"sheetId": 42, "index": 9}},
        {"deleteConditionalFormatRule": {"sheetId": 42, "index": 5}},
        {"deleteConditionalFormatRule": {"sheetId": 42, "index": 2}},
    ]


def _fake_service(sheet_id, conditional_formats):
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"sheetId": sheet_id}, "conditionalFormats": conditional_formats}]
    }
    return service


def _fake_config():
    return {"sheets_sync": {"spreadsheet_id": "sheet-id"}}


def test_run_reports_nothing_to_fix_and_does_not_write(capsys):
    fake_service = _fake_service(0, [_rule([(1, 8157, 0, 26)])])
    with (
        patch.object(consolidate_module, "load_config", return_value=_fake_config()),
        patch.object(consolidate_module, "get_sheets_service", return_value=fake_service),
        patch.object(consolidate_module, "get_sheet_id", return_value=0),
    ):
        run("OffresTest", apply=False)

    assert "Aucune regle" in capsys.readouterr().out
    fake_service.spreadsheets.return_value.batchUpdate.assert_not_called()


def test_run_dry_run_reports_fixes_without_writing(capsys):
    fake_service = _fake_service(0, [_rule([(99, 200, 1, 2), (99, 200, 17, 18)])])
    with (
        patch.object(consolidate_module, "load_config", return_value=_fake_config()),
        patch.object(consolidate_module, "get_sheets_service", return_value=fake_service),
        patch.object(consolidate_module, "get_sheet_id", return_value=0),
    ):
        run("OffresTest", apply=False)

    out = capsys.readouterr().out
    assert "1 regle(s)" in out
    assert "DRY-RUN" in out
    fake_service.spreadsheets.return_value.batchUpdate.assert_not_called()


def test_run_applies_fixes_when_apply_is_true(capsys):
    fake_service = _fake_service(0, [_rule([(99, 200, 1, 2), (99, 200, 17, 18)])])
    with (
        patch.object(consolidate_module, "load_config", return_value=_fake_config()),
        patch.object(consolidate_module, "get_sheets_service", return_value=fake_service),
        patch.object(consolidate_module, "get_sheet_id", return_value=0),
    ):
        run("OffresTest", apply=True)

    fake_service.spreadsheets.return_value.batchUpdate.assert_called_once()
    assert "supprimee(s)" in capsys.readouterr().out


def test_main_parses_sheet_name_and_defaults_apply_to_false():
    with patch.object(consolidate_module, "run") as fake_run:
        main(["OffresTest"])

    fake_run.assert_called_once_with("OffresTest", apply=False)


def test_main_parses_the_apply_flag():
    with patch.object(consolidate_module, "run") as fake_run:
        main(["OffresTest", "--apply"])

    fake_run.assert_called_once_with("OffresTest", apply=True)


def test_consolidate_deletes_b_and_r_rules_and_returns_their_indices():
    fake_service = _fake_service(0, [_rule([(99, 200, 1, 2), (99, 200, 17, 18)])])

    deleted = consolidate(fake_service, "sheet-id", sheet_id=0)

    assert deleted == [0]
    fake_service.spreadsheets.return_value.batchUpdate.assert_called_once_with(
        spreadsheetId="sheet-id",
        body={"requests": [{"deleteConditionalFormatRule": {"sheetId": 0, "index": 0}}]},
    )


def test_consolidate_returns_empty_list_and_does_not_write_when_nothing_to_delete():
    fake_service = _fake_service(0, [_rule([(1, 8157, 0, 26)])])

    deleted = consolidate(fake_service, "sheet-id", sheet_id=0)

    assert deleted == []
    fake_service.spreadsheets.return_value.batchUpdate.assert_not_called()
