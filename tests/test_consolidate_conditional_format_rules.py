from consolidate_conditional_format_rules import build_requests, find_b_and_r_only_rules


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
