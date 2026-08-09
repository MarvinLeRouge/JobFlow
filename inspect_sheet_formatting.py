#!/usr/bin/env python3
"""One-shot inspection tool: prints column B's formula (from a sample data
row), the sheet's data validation rules (the dropdown), and its row-level
conditional formatting rules, read directly from a Google Sheet via the
Sheets API.

Run this against a DUPLICATED test sheet, never the real one - its only
purpose is to discover exactly what sheets_sync.py needs to replicate, so it
can be transcribed correctly instead of guessed.

Usage:
    python3 inspect_sheet_formatting.py <spreadsheet_id> <sheet_name>
"""

import argparse
import json

from googleapiclient.discovery import build

import auth
from sheets_sync import SHEETS_SCOPES, TOKEN_SHEETS_FILE


def get_sheets_service():
    creds = auth.get_credentials(scopes=SHEETS_SCOPES, token_file=TOKEN_SHEETS_FILE)
    return build("sheets", "v4", credentials=creds)


def inspect(spreadsheet_id: str, sheet_name: str) -> dict:
    """Return the sheet metadata needed to replicate formatting: a sample of
    row 2's cell formulas/validation/format (representative of any data row),
    plus the sheet-wide conditional format rules."""
    service = get_sheets_service()
    return (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            ranges=[f"{sheet_name}!A1:Z3"],
            fields=(
                "sheets(properties,conditionalFormats,"
                "data.rowData.values(userEnteredValue,dataValidation,userEnteredFormat))"
            ),
            includeGridData=True,
        )
        .execute()
    )


def main(spreadsheet_id: str, sheet_name: str) -> None:
    result = inspect(spreadsheet_id, sheet_name)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("spreadsheet_id")
    parser.add_argument("sheet_name")
    args = parser.parse_args()
    main(args.spreadsheet_id, args.sheet_name)
