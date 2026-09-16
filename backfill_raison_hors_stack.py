#!/usr/bin/env python3
"""One-shot migration: writes "Hors stack" into column R (Raison_exclusion)
for rows whose Stack column contains an excluded tag
(extract/filters.is_hors_stack) but whose Raison_exclusion is currently
empty - offers imported before extract_eml.py auto-detected this criterion.

Run this AFTER backfill_raison_hors_profil.py: extract_eml.py's priority
order is Hors profil > Stage/Alternance > Hors stack, so rows that would
match both a blacklist term and an excluded tag must end up "Hors profil" -
running the Hors profil backfill first (leaving those rows non-empty)
ensures this script only fills what's genuinely left over.

Run this against a DUPLICATED test sheet first (e.g. "OffresTest"), never
the real one, until the result has been checked live. Run
backfill_r_dropdown.py afterward to attach the dropdown validation to the
newly written rows.

Usage:
    python3 backfill_raison_hors_stack.py <sheet_name> [--apply]

Without --apply, only prints what would change (dry-run).
"""

import argparse

from backfill_r_dropdown import read_raison_column
from extract.filters import is_hors_stack
from sheets_sync import get_sheets_service, load_config

HOMOGENIZED_VALUE = "Hors stack"


def read_stack_column(service, spreadsheet_id: str, sheet_name: str) -> list[str]:
    """Column Q's values (Stack) for every data row (row 2 onward), in row
    order. Shorter than the sheet's true row count when trailing rows are
    blank - callers only need this to align with read_raison_column, not an
    exact row count."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!Q2:Q")
        .execute()
    )
    return [row[0] if row else "" for row in result.get("values", [])]


def rows_to_fill(
    stack_values: list[str], raison_values: list[str], excluded_tags: list[str], start_row: int
) -> list[int]:
    """1-indexed row numbers whose Stack contains an excluded tag and whose
    Raison_exclusion is currently empty."""
    rows = []
    for i, stack in enumerate(stack_values):
        raison = raison_values[i] if i < len(raison_values) else ""
        if not raison and is_hors_stack(stack, excluded_tags):
            rows.append(start_row + i)
    return rows


def apply_fill(service, spreadsheet_id: str, sheet_name: str, rows: list[int]) -> None:
    """Write the homogenized value to every row in one values().batchUpdate
    call, instead of one call per row - a migration can touch hundreds of
    scattered rows, and bundling them keeps the number of Sheets API calls
    reasonable."""
    data = [{"range": f"{sheet_name}!R{row}", "values": [[HOMOGENIZED_VALUE]]} for row in rows]
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"valueInputOption": "RAW", "data": data}
    ).execute()


def run(sheet_name: str, apply: bool) -> None:
    config = load_config()
    spreadsheet_id = config["sheets_sync"]["spreadsheet_id"]
    excluded_tags = config.get("hors_stack_tags", [])

    service = get_sheets_service()
    stack_values = read_stack_column(service, spreadsheet_id, sheet_name)
    raison_values = read_raison_column(service, spreadsheet_id, sheet_name)
    rows = rows_to_fill(stack_values, raison_values, excluded_tags, start_row=2)

    if not rows:
        print(f"Aucune ligne a corriger dans {sheet_name!r}.")
        return

    print(f"{len(rows)} ligne(s) a corriger dans {sheet_name!r} : {rows}")

    if not apply:
        print("[DRY-RUN] Rien ecrit. Relancer avec --apply pour ecrire.")
        return

    apply_fill(service, spreadsheet_id, sheet_name, rows)
    print(f"{len(rows)} ligne(s) mises a jour vers {HOMOGENIZED_VALUE!r}.")


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
