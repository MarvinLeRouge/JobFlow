#!/usr/bin/env python3
"""One-shot migration: writes "Stage/Alternance" into column R
(Raison_exclusion) for rows whose title matches the stage/alternance
criteria (extract/filters.is_stage_alternance) but whose Raison_exclusion is
currently empty - offers imported before extract_eml.py auto-detected this
criterion, previously flagged only by a conditional format rule on the
title, not by an actual Raison_exclusion value.

Run this against a DUPLICATED test sheet first (e.g. "OffresTest"), never
the real one, until the result has been checked live. Run
backfill_r_dropdown.py afterward to attach the dropdown validation to the
newly written rows.

Usage:
    python3 backfill_raison_stage_alternance.py <sheet_name> [--apply]

Without --apply, only prints what would change (dry-run).
"""

import argparse

from backfill_r_dropdown import read_raison_column
from extract.filters import is_stage_alternance
from sheets_sync import get_sheets_service, load_config

HOMOGENIZED_VALUE = "Stage/Alternance"


def read_titre_column(service, spreadsheet_id: str, sheet_name: str) -> list[str]:
    """Column E's values (Titre) for every data row (row 2 onward), in row
    order. Shorter than the sheet's true row count when trailing rows are
    blank - callers only need this to align with read_raison_column, not an
    exact row count."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!E2:E")
        .execute()
    )
    return [row[0] if row else "" for row in result.get("values", [])]


def rows_to_fill(
    titre_values: list[str], raison_values: list[str], terms: list[str], start_row: int
) -> list[int]:
    """1-indexed row numbers whose title matches the stage/alternance
    criteria and whose Raison_exclusion is currently empty."""
    rows = []
    for i, titre in enumerate(titre_values):
        raison = raison_values[i] if i < len(raison_values) else ""
        if not raison and is_stage_alternance(titre, terms):
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
    terms = config.get("stage_alternance_titres", [])

    service = get_sheets_service()
    titre_values = read_titre_column(service, spreadsheet_id, sheet_name)
    raison_values = read_raison_column(service, spreadsheet_id, sheet_name)
    rows = rows_to_fill(titre_values, raison_values, terms, start_row=2)

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
