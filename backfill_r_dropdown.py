#!/usr/bin/env python3
"""One-shot migration: attaches column R's (Raison_exclusion) dropdown
validation to existing rows whose current text already matches one of the
dropdown's exact items, without touching the cell's value or color.

Rows written before extract_eml.py started emitting exact dropdown values
(Stage/Alternance, Hors stack) show that text as plain, unvalidated content
instead of a selected dropdown item. Run this once against a target sheet
to fix them retroactively. Rows with an empty or freeform value (e.g. a
blacklist marker) are left untouched.

Run this against a DUPLICATED test sheet first (e.g. "OffresTest"), never
the real one, until the result has been checked live.

Usage:
    python3 backfill_r_dropdown.py <sheet_name> [--apply]

Without --apply, only prints what would change (dry-run).
"""

import argparse

from sheets_sync import get_sheet_id, get_sheets_service, load_config


def fetch_dropdown_values(
    service, spreadsheet_id: str, reference_sheet_name: str, reference_row: int
) -> list[str]:
    """The exact list of column R dropdown items, read live from the
    reference cell's data validation rule rather than hardcoded, so this
    stays correct if the dropdown's items are ever edited in Sheets."""
    result = (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            ranges=[f"{reference_sheet_name}!B{reference_row}"],
            fields="sheets.data.rowData.values.dataValidation",
            includeGridData=True,
        )
        .execute()
    )
    cell = result["sheets"][0]["data"][0]["rowData"][0]["values"][0]
    return [v["userEnteredValue"] for v in cell["dataValidation"]["condition"]["values"]]


def read_raison_column(service, spreadsheet_id: str, sheet_name: str) -> list[str]:
    """Column R's values for every data row (row 2 onward), in row order.
    Shorter than the sheet's true row count when trailing rows are blank -
    callers only need this to build ranges, not an exact row count."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!R2:R")
        .execute()
    )
    return [row[0] if row else "" for row in result.get("values", [])]


def rows_needing_backfill(
    raison_values: list[str], valid_values: set[str], start_row: int
) -> list[tuple[int, int]]:
    """Contiguous (start, end) 1-indexed row ranges whose current
    Raison_exclusion text is a non-empty exact match of one of the
    dropdown's items - these are the rows to attach validation to. Empty
    cells and freeform text (e.g. a blacklist marker) are left untouched."""
    ranges = []
    range_start = None
    for i, value in enumerate(raison_values):
        row_number = start_row + i
        if value in valid_values:
            if range_start is None:
                range_start = row_number
        else:
            if range_start is not None:
                ranges.append((range_start, row_number - 1))
                range_start = None
    if range_start is not None:
        ranges.append((range_start, start_row + len(raison_values) - 1))
    return ranges


def _copy_data_validation_request(
    sheet_id: int,
    reference_sheet_id: int,
    reference_row: int,
    column_index: int,
    start_row: int,
    end_row: int,
) -> dict:
    """One copyPaste request (PASTE_DATA_VALIDATION only) copying column R's
    dropdown validation from the reference cell onto a column range
    (1-indexed rows, inclusive), without touching the destination cells'
    existing value or color. Unlike setDataValidation, which rebuilds a
    rule through the public DataValidationRule schema, this duplicates the
    reference cell's internal validation state as-is - the only way to
    reproduce its colored-chip styling, which the Sheets API doesn't expose
    or accept through that schema at all (confirmed: a ONE_OF_LIST rule
    built via setDataValidation with the exact same items renders as a
    plain, uncolored dropdown)."""
    return {
        "copyPaste": {
            "source": {
                "sheetId": reference_sheet_id,
                "startRowIndex": reference_row - 1,
                "endRowIndex": reference_row,
                "startColumnIndex": 1,
                "endColumnIndex": 2,
            },
            "destination": {
                "sheetId": sheet_id,
                "startRowIndex": start_row - 1,
                "endRowIndex": end_row,
                "startColumnIndex": column_index,
                "endColumnIndex": column_index + 1,
            },
            "pasteType": "PASTE_DATA_VALIDATION",
        }
    }


def apply_dropdown_validation(
    service,
    spreadsheet_id: str,
    sheet_id: int,
    reference_sheet_id: int,
    reference_row: int,
    column_index: int,
    ranges: list[tuple[int, int]],
) -> None:
    """Copy the reference cell's dropdown validation onto every range in one
    batchUpdate call, instead of one call per range - a backfill can
    involve hundreds of ranges, and bundling them keeps the number of
    Sheets API calls reasonable."""
    requests = [
        _copy_data_validation_request(
            sheet_id, reference_sheet_id, reference_row, column_index, start, end
        )
        for start, end in ranges
    ]
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()


def run(sheet_name: str, apply: bool) -> None:
    config = load_config()
    sync_config = config["sheets_sync"]
    spreadsheet_id = sync_config["spreadsheet_id"]
    reference_sheet_name = sync_config["reference_sheet_name"]
    reference_row_r = sync_config["reference_row_r"]
    raison_col_index = config["offres_csv_headers"].index("Raison_exclusion")

    service = get_sheets_service()
    sheet_id = get_sheet_id(service, spreadsheet_id, sheet_name)
    reference_sheet_id = get_sheet_id(service, spreadsheet_id, reference_sheet_name)

    valid_values = fetch_dropdown_values(
        service, spreadsheet_id, reference_sheet_name, reference_row_r
    )
    raison_values = read_raison_column(service, spreadsheet_id, sheet_name)
    ranges = rows_needing_backfill(raison_values, set(valid_values), start_row=2)

    if not ranges:
        print(f"Aucune ligne a corriger dans {sheet_name!r}.")
        return

    total_rows = sum(end - start + 1 for start, end in ranges)
    print(f"{total_rows} ligne(s) sur {len(ranges)} plage(s) a corriger dans {sheet_name!r} :")
    for start, end in ranges:
        print(f"  R{start}:R{end}")

    if not apply:
        print("[DRY-RUN] Rien ecrit. Relancer avec --apply pour ecrire.")
        return

    apply_dropdown_validation(
        service,
        spreadsheet_id,
        sheet_id,
        reference_sheet_id,
        reference_row_r,
        raison_col_index,
        ranges,
    )
    print(f"Validation appliquee sur {len(ranges)} plage(s).")


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
