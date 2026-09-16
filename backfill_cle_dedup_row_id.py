#!/usr/bin/env python3
"""One-shot migration: replaces the legacy "inconnu"/"inconnue" placeholder
segments in column G (Cle_dedup) with the row's own ID - the fallback
extract/filters.build_cle_dedup() now uses for an empty entreprise/ville/
titre field, instead of a generic placeholder shared by every offer with
that field missing (which caused false duplicate matches between distinct
offers).

Run this against a DUPLICATED test sheet first (e.g. "OffresTest"), never
the real one, until the result has been checked live.

Usage:
    python3 backfill_cle_dedup_row_id.py <sheet_name> [--apply]

Without --apply, only prints what would change (dry-run).
"""

import argparse

from sheets_sync import get_sheets_service, load_config

PLACEHOLDER_VALUES = frozenset({"inconnu", "inconnue"})


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


def rows_to_fix(
    id_values: list[str], cle_dedup_values: list[str], start_row: int
) -> list[tuple[int, str]]:
    """(row_number, corrected_cle_dedup) for every row whose Cle_dedup has
    at least one "inconnu"/"inconnue" placeholder segment - each such
    segment is replaced with the row's own ID, the other segments left
    untouched."""
    fixes = []
    for i, cle in enumerate(cle_dedup_values):
        segments = cle.split("|")
        if not any(segment in PLACEHOLDER_VALUES for segment in segments):
            continue
        row_id = id_values[i] if i < len(id_values) else ""
        new_segments = [
            row_id if segment in PLACEHOLDER_VALUES else segment for segment in segments
        ]
        fixes.append((start_row + i, "|".join(new_segments)))
    return fixes


def apply_fix(service, spreadsheet_id: str, sheet_name: str, fixes: list[tuple[int, str]]) -> None:
    """Write every corrected Cle_dedup in one values().batchUpdate call,
    instead of one call per row - a migration can touch thousands of
    scattered rows, and bundling them keeps the number of Sheets API calls
    reasonable."""
    data = [{"range": f"{sheet_name}!G{row}", "values": [[cle]]} for row, cle in fixes]
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"valueInputOption": "RAW", "data": data}
    ).execute()


def run(sheet_name: str, apply: bool) -> None:
    config = load_config()
    spreadsheet_id = config["sheets_sync"]["spreadsheet_id"]

    service = get_sheets_service()
    id_values = read_id_column(service, spreadsheet_id, sheet_name)
    cle_dedup_values = read_cle_dedup_column(service, spreadsheet_id, sheet_name)
    fixes = rows_to_fix(id_values, cle_dedup_values, start_row=2)

    if not fixes:
        print(f"Aucune ligne a corriger dans {sheet_name!r}.")
        return

    print(f"{len(fixes)} ligne(s) a corriger dans {sheet_name!r}.")

    if not apply:
        print("[DRY-RUN] Rien ecrit. Relancer avec --apply pour ecrire.")
        return

    apply_fix(service, spreadsheet_id, sheet_name, fixes)
    print(f"{len(fixes)} ligne(s) mises a jour.")


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
