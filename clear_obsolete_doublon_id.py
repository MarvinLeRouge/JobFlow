#!/usr/bin/env python3
"""One-shot migration: clears column H (Doublon_ID) for rows whose current
Cle_dedup no longer matches the Cle_dedup of the row it points to - a
leftover from backfill_cle_dedup_row_id.py, which replaced the legacy
"inconnu"/"inconnue" placeholder segments in Cle_dedup and, as a side
effect, broke duplicate matches that only existed because two distinct
offers shared the same placeholder.

Run this AFTER backfill_cle_dedup_row_id.py, against a DUPLICATED test
sheet first (e.g. "OffresTest"), never the real one, until the result has
been checked live.

Usage:
    python3 clear_obsolete_doublon_id.py <sheet_name> [--apply]

Without --apply, only prints what would change (dry-run).
"""

import argparse

from sheets_sync import get_sheets_service, load_config


def read_id_column(service, spreadsheet_id: str, sheet_name: str) -> list[str]:
    """Column A's values (ID) for every data row (row 2 onward), in row
    order."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A2:A")
        .execute()
    )
    return [row[0] if row else "" for row in result.get("values", [])]


def read_cle_dedup_column(service, spreadsheet_id: str, sheet_name: str) -> list[str]:
    """Column G's values (Cle_dedup) for every data row (row 2 onward), in
    row order."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!G2:G")
        .execute()
    )
    return [row[0] if row else "" for row in result.get("values", [])]


def read_doublon_id_column(service, spreadsheet_id: str, sheet_name: str) -> list[str]:
    """Column H's values (Doublon_ID) for every data row (row 2 onward), in
    row order."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!H2:H")
        .execute()
    )
    return [row[0] if row else "" for row in result.get("values", [])]


def rows_to_clear(
    id_values: list[str],
    cle_dedup_values: list[str],
    doublon_id_values: list[str],
    start_row: int,
) -> list[int]:
    """1-indexed row numbers whose Doublon_ID is now obsolete: either it
    points to a row whose current Cle_dedup no longer matches this row's
    own, or it points to an unknown row entirely."""
    id_to_cle = {rid: cle for rid, cle in zip(id_values, cle_dedup_values) if rid}
    rows = []
    for i, doublon_id in enumerate(doublon_id_values):
        if not doublon_id:
            continue
        cle = cle_dedup_values[i] if i < len(cle_dedup_values) else ""
        ref_cle = id_to_cle.get(doublon_id)
        if ref_cle != cle:
            rows.append(start_row + i)
    return rows


def apply_clear(service, spreadsheet_id: str, sheet_name: str, rows: list[int]) -> None:
    """Clear Doublon_ID for every row in one values().batchUpdate call,
    instead of one call per row - a migration can touch thousands of
    scattered rows, and bundling them keeps the number of Sheets API calls
    reasonable."""
    data = [{"range": f"{sheet_name}!H{row}", "values": [[""]]} for row in rows]
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"valueInputOption": "RAW", "data": data}
    ).execute()


def run(sheet_name: str, apply: bool) -> None:
    config = load_config()
    spreadsheet_id = config["sheets_sync"]["spreadsheet_id"]

    service = get_sheets_service()
    id_values = read_id_column(service, spreadsheet_id, sheet_name)
    cle_dedup_values = read_cle_dedup_column(service, spreadsheet_id, sheet_name)
    doublon_id_values = read_doublon_id_column(service, spreadsheet_id, sheet_name)
    rows = rows_to_clear(id_values, cle_dedup_values, doublon_id_values, start_row=2)

    if not rows:
        print(f"Aucune ligne a corriger dans {sheet_name!r}.")
        return

    print(f"{len(rows)} ligne(s) a corriger dans {sheet_name!r}.")

    if not apply:
        print("[DRY-RUN] Rien ecrit. Relancer avec --apply pour ecrire.")
        return

    apply_clear(service, spreadsheet_id, sheet_name, rows)
    print(f"{len(rows)} ligne(s) videes.")


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
