#!/usr/bin/env python3
"""One-shot migration: rewrites legacy blacklist markers in column R
(Raison_exclusion) - "Blacklisté: <category>" - to "Hors profil", the
homogenized value extract_eml.py now writes for every blacklisted offer.
The precise term stays available in the Notes column, so nothing is lost.

Run this against a DUPLICATED test sheet first (e.g. "OffresTest"), never
the real one, until the result has been checked live. Run
backfill_r_dropdown.py afterward to attach the dropdown validation to the
rewritten rows.

Usage:
    python3 migrate_raison_exclusion_hors_profil.py <sheet_name> [--apply]

Without --apply, only prints what would change (dry-run).
"""

import argparse

from backfill_r_dropdown import read_raison_column
from sheets_sync import get_sheets_service, load_config

LEGACY_BLACKLIST_PREFIX = "Blacklisté: "
HOMOGENIZED_VALUE = "Hors profil"


def rows_to_rewrite(raison_values: list[str], start_row: int) -> list[int]:
    """1-indexed row numbers whose current text is a legacy blacklist
    marker that should become the homogenized value."""
    return [
        start_row + i
        for i, value in enumerate(raison_values)
        if value.startswith(LEGACY_BLACKLIST_PREFIX)
    ]


def apply_rewrite(service, spreadsheet_id: str, sheet_name: str, rows: list[int]) -> None:
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

    service = get_sheets_service()
    raison_values = read_raison_column(service, spreadsheet_id, sheet_name)
    rows = rows_to_rewrite(raison_values, start_row=2)

    if not rows:
        print(f"Aucune ligne a corriger dans {sheet_name!r}.")
        return

    print(f"{len(rows)} ligne(s) a corriger dans {sheet_name!r} : {rows}")

    if not apply:
        print("[DRY-RUN] Rien ecrit. Relancer avec --apply pour ecrire.")
        return

    apply_rewrite(service, spreadsheet_id, sheet_name, rows)
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
