#!/usr/bin/env python3
"""Syncs new offers from the latest output/import_YYYYMMDD.csv into a Google
Sheet: appends rows the sheet doesn't already have (compared by offer ID),
reproduces column B's formula/dropdown, and extends row-level conditional
formatting to the new rows. Gated behind a persistent error state after a
failed run (see check_error_gate/write_error_state/clear_error_state).

Usage:
    python3 sheets_sync.py [--dry-run]
    python3 sheets_sync.py --ack-error
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "config" / "config.json"
LOGS_DIR = ROOT / "logs"
OUTPUT_DIR = ROOT / "output"

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TOKEN_SHEETS_FILE = ROOT / "token_sheets.json"


def load_config() -> dict:
    with CONFIG_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def offer_id_number(offer_id: str) -> int:
    """'E006545' -> 6545. Raises ValueError on an unexpected format."""
    if not offer_id.startswith("E") or not offer_id[1:].isdigit():
        raise ValueError(f"Unexpected offer ID format: {offer_id!r}")
    return int(offer_id[1:])


def read_import_rows(import_csv_path: Path) -> list[dict]:
    """Read an output/import_YYYYMMDD.csv file's rows as dicts."""
    with import_csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter=";"))


def rows_to_sync(import_rows: list[dict], last_synced_id: int) -> list[dict]:
    """Rows whose ID is strictly greater than last_synced_id, in CSV order."""
    return [row for row in import_rows if offer_id_number(row["ID"]) > last_synced_id]


def read_last_synced_id(service, spreadsheet_id: str, sheet_name: str) -> int:
    """Highest offer ID number currently in column A of the sheet, or 0 if
    the sheet has no data rows yet."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A2:A")
        .execute()
    )
    values = result.get("values", [])
    ids = [offer_id_number(row[0]) for row in values if row]
    return max(ids) if ids else 0
