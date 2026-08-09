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
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

import auth

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "config" / "config.json"
LOGS_DIR = ROOT / "logs"
OUTPUT_DIR = ROOT / "output"

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TOKEN_SHEETS_FILE = ROOT / "token_sheets.json"

ERROR_STATE_FILE = LOGS_DIR / "sheets_sync_error.json"

LOCAL_TZ = ZoneInfo("Europe/Paris")


def write_error_state(message: str) -> None:
    ERROR_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ERROR_STATE_FILE.write_text(
        json.dumps(
            {
                "message": message,
                "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        ),
        encoding="utf-8",
    )


def read_error_state() -> dict | None:
    if not ERROR_STATE_FILE.exists():
        return None
    with ERROR_STATE_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def clear_error_state() -> None:
    ERROR_STATE_FILE.unlink(missing_ok=True)


def check_error_gate() -> None:
    """Raise SystemExit with the recorded error if an unacknowledged sync
    failure exists. Called at the start of sheets_sync's own run() and of
    run_pipeline.run_pipeline()."""
    state = read_error_state()
    if state is not None:
        raise SystemExit(
            f"Synchronisation Sheets bloquee : erreur non acquittee du {state['recorded_at']}\n"
            f"  {state['message']}\n"
            f"Acquitte avec : python3 sheets_sync.py --ack-error"
        )


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


def get_sheets_service():
    creds = auth.get_credentials(scopes=SHEETS_SCOPES, token_file=TOKEN_SHEETS_FILE)
    return build("sheets", "v4", credentials=creds)


def get_sheet_id(service, spreadsheet_id: str, sheet_name: str) -> int:
    """Numeric sheetId for a given tab name."""
    meta = (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets.properties")
        .execute()
    )
    for sheet in meta["sheets"]:
        if sheet["properties"]["title"] == sheet_name:
            return sheet["properties"]["sheetId"]
    raise ValueError(f"Sheet tab not found: {sheet_name!r}")


def get_last_data_row(service, spreadsheet_id: str, sheet_name: str) -> int:
    """1-indexed sheet row number of the last row containing data (row 1 is
    the header). Returns 1 for a header-only sheet."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A:A")
        .execute()
    )
    return len(result.get("values", []))


def row_values(row: dict, headers: list[str], row_number: int) -> list:
    """Ordered cell values for one CSV row, in the sheet's column order.
    The 'Traite' column is always replaced with the live formula
    '=R{row_number}<>""' instead of the CSV's static default, so it stays
    driven by column R rather than a fixed value."""
    values = [row.get(h, "") for h in headers]
    traite_index = headers.index("Traite")
    values[traite_index] = f'=R{row_number}<>""'
    return values


def ensure_sheet_rows(service, spreadsheet_id: str, sheet_id: int, needed_row_count: int) -> None:
    """Grow the sheet's grid if it doesn't already have at least
    needed_row_count rows. A Sheets grid has a fixed row count that must be
    explicitly extended via appendDimension before writing beyond it -
    copyPaste/values.update both fail with a 400 error otherwise (confirmed
    live against the duplicated test sheet)."""
    meta = (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties.sheetId,properties.gridProperties.rowCount)",
        )
        .execute()
    )
    sheet = next(s for s in meta["sheets"] if s["properties"]["sheetId"] == sheet_id)
    current_row_count = sheet["properties"]["gridProperties"]["rowCount"]

    if needed_row_count <= current_row_count:
        return

    body = {
        "requests": [
            {
                "appendDimension": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "length": needed_row_count - current_row_count,
                }
            }
        ]
    }
    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()


def copy_reference_formatting(
    service,
    spreadsheet_id: str,
    sheet_id: int,
    reference_sheet_id: int,
    reference_row: int,
    column_index: int,
    start_row: int,
    end_row: int,
) -> None:
    """Copy one column's dropdown validation and colors (plus a disposable
    placeholder value) from a reference cell in the References tab onto
    rows [start_row, end_row] (1-indexed, inclusive) of the given 0-indexed
    column. The placeholder value gets overwritten by write_new_rows() right
    after - a plain values.update never disturbs validation/format,
    confirmed live against the duplicated test sheet."""
    body = {
        "requests": [
            {
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
                    "pasteType": "PASTE_NORMAL",
                }
            }
        ]
    }
    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()


def rows_needing_r_dropdown(rows: list[dict], start_row: int) -> list[tuple[int, int]]:
    """Contiguous (start, end) 1-indexed row ranges among the new rows whose
    Raison_exclusion is empty - only these rows should get column R's
    dropdown validation applied. Rows with a pre-filled exclusion reason
    (e.g. extract_eml.py's blacklist marker) keep their plain value with no
    validation, so Sheets never shows a 'not in list' warning triangle on
    an automatically-determined value - confirmed needed live, the warning
    appeared on a row whose Raison_exclusion came from the CSV, not from
    the user picking a dropdown option."""
    ranges = []
    range_start = None
    for i, row in enumerate(rows):
        row_number = start_row + i
        if not row.get("Raison_exclusion", ""):
            if range_start is None:
                range_start = row_number
        else:
            if range_start is not None:
                ranges.append((range_start, row_number - 1))
                range_start = None
    if range_start is not None:
        ranges.append((range_start, start_row + len(rows) - 1))
    return ranges


def rows_needing_r_clear(rows: list[dict], start_row: int) -> list[tuple[int, int]]:
    """Contiguous 1-indexed row ranges among the new rows whose
    Raison_exclusion is non-empty - these need column R's data validation
    explicitly cleared. Newly appended rows can inherit stale dropdown
    validation from the row above them regardless of what gets explicitly
    copied afterward - confirmed live: a row deliberately excluded from
    rows_needing_r_dropdown's copy still showed the inherited validation
    until cleared."""
    ranges = []
    range_start = None
    for i, row in enumerate(rows):
        row_number = start_row + i
        if row.get("Raison_exclusion", ""):
            if range_start is None:
                range_start = row_number
        else:
            if range_start is not None:
                ranges.append((range_start, row_number - 1))
                range_start = None
    if range_start is not None:
        ranges.append((range_start, start_row + len(rows) - 1))
    return ranges


def clear_data_validation(
    service,
    spreadsheet_id: str,
    sheet_id: int,
    column_index: int,
    start_row: int,
    end_row: int,
) -> None:
    """Explicitly remove any data validation from a column range (1-indexed
    rows, inclusive), via a setDataValidation request with no rule - Sheets
    interprets the absence of a rule as 'clear validation for this range'."""
    body = {
        "requests": [
            {
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": start_row - 1,
                        "endRowIndex": end_row,
                        "startColumnIndex": column_index,
                        "endColumnIndex": column_index + 1,
                    },
                }
            }
        ]
    }
    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()


def write_new_rows(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    rows: list[dict],
    headers: list[str],
    start_row: int,
) -> None:
    """Write the final values for rows into columns A..(last header),
    starting at start_row (1-indexed). Must run AFTER
    copy_reference_formatting for columns B and R, so this write's values
    (including the correct per-row Traite formula) become the final content
    without disturbing the validation/colors copied a moment earlier."""
    if not rows:
        return
    end_row = start_row + len(rows) - 1
    last_col = chr(ord("A") + len(headers) - 1)
    values = [row_values(row, headers, row_number=start_row + i) for i, row in enumerate(rows)]
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A{start_row}:{last_col}{end_row}",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()


def latest_import_csv(today: str | None = None) -> Path | None:
    """Path to today's output/import_YYYYMMDD.csv, or None if it doesn't
    exist (e.g. extract_eml.py found nothing new to write this run)."""
    if today is None:
        today = datetime.now(LOCAL_TZ).strftime("%Y%m%d")
    path = OUTPUT_DIR / f"import_{today}.csv"
    return path if path.exists() else None


def run(dry_run: bool, today: str | None = None) -> None:
    check_error_gate()

    config = load_config()
    sync_config = config["sheets_sync"]
    spreadsheet_id = sync_config["spreadsheet_id"]
    sheet_name = sync_config["sheet_name"]
    reference_sheet_name = sync_config["reference_sheet_name"]
    reference_row_b = sync_config["reference_row_b"]
    reference_row_r = sync_config["reference_row_r"]
    headers = config["offres_csv_headers"]

    import_csv = latest_import_csv(today=today)
    if import_csv is None:
        print("Aucun fichier d'import a synchroniser aujourd'hui.")
        return

    import_rows = read_import_rows(import_csv)

    try:
        service = get_sheets_service()
        sheet_id = get_sheet_id(service, spreadsheet_id, sheet_name)
        reference_sheet_id = get_sheet_id(service, spreadsheet_id, reference_sheet_name)

        last_synced_id = read_last_synced_id(service, spreadsheet_id, sheet_name)
        new_rows = rows_to_sync(import_rows, last_synced_id)

        if not new_rows:
            print("Aucune nouvelle offre a synchroniser (deja a jour).")
            return

        print(
            f"{len(new_rows)} nouvelle(s) offre(s) a synchroniser "
            f"(IDs {new_rows[0]['ID']} a {new_rows[-1]['ID']})"
        )

        if dry_run:
            print("[DRY-RUN] Rien ecrit.")
            return

        template_row = get_last_data_row(service, spreadsheet_id, sheet_name)
        start_row = template_row + 1
        end_row = start_row + len(new_rows) - 1

        ensure_sheet_rows(service, spreadsheet_id, sheet_id, needed_row_count=end_row)

        traite_col_index = headers.index("Traite")
        raison_col_index = headers.index("Raison_exclusion")

        copy_reference_formatting(
            service,
            spreadsheet_id,
            sheet_id,
            reference_sheet_id,
            reference_row_b,
            traite_col_index,
            start_row,
            end_row,
        )
        for r_start, r_end in rows_needing_r_dropdown(new_rows, start_row):
            copy_reference_formatting(
                service,
                spreadsheet_id,
                sheet_id,
                reference_sheet_id,
                reference_row_r,
                raison_col_index,
                r_start,
                r_end,
            )
        for r_start, r_end in rows_needing_r_clear(new_rows, start_row):
            clear_data_validation(
                service,
                spreadsheet_id,
                sheet_id,
                raison_col_index,
                r_start,
                r_end,
            )
        write_new_rows(service, spreadsheet_id, sheet_name, new_rows, headers, start_row)

        print(
            f"{len(new_rows)} offre(s) synchronisee(s) dans {sheet_name} "
            f"(lignes {start_row}-{end_row})"
        )
    except Exception as e:
        write_error_state(str(e))
        raise
