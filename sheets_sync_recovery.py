#!/usr/bin/env python3
"""Reconciles the production Google Sheet's offer-ID column A against the
local output/offres.csv archive (the ID-contiguous source of truth): finds
any ID present locally but missing from the sheet - whether an internal gap
or a lagging tail - and backfills it, appended at the sheet's current end,
each missing contiguous ID sequence preceded by one blank separator row so
it is visually distinguishable from a normal same-day batch.

Usage:
    python3 sheets_sync_recovery.py --dry-run
    python3 sheets_sync_recovery.py
"""

import argparse
import csv
from pathlib import Path

import sheets_sync

ROOT = Path(__file__).parent
OFFRES_CSV = ROOT / "output" / "offres.csv"


def read_local_offers(offres_csv_path: Path) -> dict[int, dict]:
    """Read output/offres.csv into {id_number: row_dict}. Raises ValueError
    if the local archive itself has a gap - offres.csv is expected to be
    perfectly ID-contiguous from 1 (one row per offer ever extracted), so a
    gap there is a distinct, more serious anomaly this script does not try
    to silently patch."""
    with offres_csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    offers = {sheets_sync.offer_id_number(row["ID"]): row for row in rows}
    expected = set(range(1, len(offers) + 1))
    if set(offers) != expected:
        raise ValueError(
            f"Discontinuite dans l'archive locale {offres_csv_path} elle-meme "
            "(devrait etre continue de E000001 a la derniere offre) - a "
            "investiguer separement avant de rattraper le sheet."
        )
    return offers


def read_sheet_ids(service, spreadsheet_id: str, sheet_name: str) -> set[int]:
    """Numeric offer IDs currently present anywhere in column A (row 2
    onward - row 1 is the header)."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A2:A")
        .execute()
    )
    values = result.get("values", [])
    return {sheets_sync.offer_id_number(row[0]) for row in values if row}


def missing_id_sequences(sheet_ids: set[int], local_max: int) -> list[list[int]]:
    """Contiguous ascending runs of IDs in [1, local_max] absent from
    sheet_ids, in ascending order."""
    sequences = []
    current: list[int] = []
    for i in range(1, local_max + 1):
        if i in sheet_ids:
            if current:
                sequences.append(current)
                current = []
        else:
            current.append(i)
    if current:
        sequences.append(current)
    return sequences


def run(dry_run: bool) -> None:
    config = sheets_sync.load_config()
    sync_config = config["sheets_sync"]
    spreadsheet_id = sync_config["spreadsheet_id"]
    sheet_name = sync_config["sheet_name"]
    reference_sheet_name = sync_config["reference_sheet_name"]
    reference_row_b = sync_config["reference_row_b"]
    reference_row_r = sync_config["reference_row_r"]
    headers = config["offres_csv_headers"]

    local_offers = read_local_offers(OFFRES_CSV)
    local_max = max(local_offers) if local_offers else 0

    service = sheets_sync.get_sheets_service()
    sheet_ids = read_sheet_ids(service, spreadsheet_id, sheet_name)

    sequences = missing_id_sequences(sheet_ids, local_max)
    if not sequences:
        print("Aucune discontinuite : le sheet est aligne avec l'archive locale.")
        return

    highest_synced = max(sheet_ids, default=0)
    for seq in sequences:
        kind = "fin du sheet en retard" if seq[0] > highest_synced else "trou interne"
        print(f"{len(seq)} offre(s) manquante(s) ({kind}) : E{seq[0]:06d} a E{seq[-1]:06d}")

    if dry_run:
        print("[DRY-RUN] Rien ecrit.")
        return

    sheet_id = sheets_sync.get_sheet_id(service, spreadsheet_id, sheet_name)
    reference_sheet_id = sheets_sync.get_sheet_id(service, spreadsheet_id, reference_sheet_name)
    traite_col_index = headers.index("Traite")
    raison_col_index = headers.index("Raison_exclusion")

    for seq in sequences:
        rows = [local_offers[i] for i in seq]

        separator_row = sheets_sync.get_last_data_row(service, spreadsheet_id, sheet_name) + 1
        start_row = separator_row + 1
        end_row = start_row + len(rows) - 1

        sheets_sync.ensure_sheet_rows(service, spreadsheet_id, sheet_id, needed_row_count=end_row)

        sheets_sync.copy_reference_formatting(
            service,
            spreadsheet_id,
            sheet_id,
            reference_sheet_id,
            reference_row_b,
            traite_col_index,
            start_row,
            end_row,
        )
        for r_start, r_end in sheets_sync.rows_needing_r_dropdown(rows, start_row):
            sheets_sync.copy_reference_formatting(
                service,
                spreadsheet_id,
                sheet_id,
                reference_sheet_id,
                reference_row_r,
                raison_col_index,
                r_start,
                r_end,
            )
        for r_start, r_end in sheets_sync.rows_needing_r_clear(rows, start_row):
            sheets_sync.clear_data_validation(
                service, spreadsheet_id, sheet_id, raison_col_index, r_start, r_end
            )
        sheets_sync.write_new_rows(service, spreadsheet_id, sheet_name, rows, headers, start_row)
        sheets_sync.extend_conditional_format_ranges(
            service, spreadsheet_id, sheet_id, new_end_row=end_row
        )

        print(
            f"{len(rows)} offre(s) ecrite(s) dans {sheet_name} (lignes {start_row}-{end_row}, "
            f"ligne {separator_row} laissee vide en separateur)"
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
