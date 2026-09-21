#!/usr/bin/env python3
"""One-shot cleanup: deletes conditional format rules on the Offres sheet
scoped to exactly columns B and R - leftover copy-paste artifacts that
dragged the origin cell's formatting along with the pasted value. Each one
is redundant: the same highlight is already produced by the corresponding
whole-row rule (columns A-Z), which already covers the full row range with
the same background color.

Usage:
    python3 consolidate_conditional_format_rules.py <sheet_name> [--apply]

Without --apply, only prints what would change (dry-run).
"""

import argparse

from sheets_sync import get_sheet_id, get_sheets_service, load_config

B_AND_R_ONLY_SCOPE = frozenset({(1, 2), (17, 18)})


def _column_scope(rule: dict) -> frozenset:
    return frozenset((r["startColumnIndex"], r["endColumnIndex"]) for r in rule.get("ranges", []))


def find_b_and_r_only_rules(rules: list[dict]) -> list[int]:
    """Indices of every rule whose ranges touch only columns B and R -
    redundant with the equivalent whole-row rule, regardless of how many
    such instances exist."""
    return [index for index, rule in enumerate(rules) if _column_scope(rule) == B_AND_R_ONLY_SCOPE]


def build_requests(sheet_id: int, indices: list[int]) -> list[dict]:
    """One deleteConditionalFormatRule per index, ordered from highest to
    lowest (required: deletions shift subsequent indices within the same
    batch)."""
    return [
        {"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": index}}
        for index in sorted(indices, reverse=True)
    ]


def fetch_rules(service, spreadsheet_id: str, sheet_id: int) -> list[dict]:
    meta = (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets(properties.sheetId,conditionalFormats)")
        .execute()
    )
    sheet = next(s for s in meta["sheets"] if s["properties"]["sheetId"] == sheet_id)
    return sheet.get("conditionalFormats", [])


def consolidate(service, spreadsheet_id: str, sheet_id: int) -> list[int]:
    """Delete every B+R-only redundant rule on the given sheet and return
    the indices that were deleted (empty if none) - the reusable building
    block behind both the standalone CLI's --apply and the automatic call
    made right after a sync run, so a copy-paste artifact never survives
    past the sync that follows it."""
    rules = fetch_rules(service, spreadsheet_id, sheet_id)
    indices = find_b_and_r_only_rules(rules)
    if not indices:
        return []

    requests = build_requests(sheet_id, indices)
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()
    return indices


def run(sheet_name: str, apply: bool) -> None:
    config = load_config()
    spreadsheet_id = config["sheets_sync"]["spreadsheet_id"]

    service = get_sheets_service()
    sheet_id = get_sheet_id(service, spreadsheet_id, sheet_name)

    rules = fetch_rules(service, spreadsheet_id, sheet_id)
    indices = find_b_and_r_only_rules(rules)
    if not indices:
        print(f"Aucune regle B+R redondante dans {sheet_name!r}.")
        return

    print(f"{len(indices)} regle(s) B+R redondante(s) a supprimer dans {sheet_name!r} : {indices}")

    if not apply:
        print("[DRY-RUN] Rien modifie. Relancer avec --apply pour ecrire.")
        return

    requests = build_requests(sheet_id, indices)
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()
    print(f"{len(indices)} regle(s) supprimee(s).")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("sheet_name")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    run(args.sheet_name, apply=args.apply)


if __name__ == "__main__":
    main()
