#!/usr/bin/env python3
"""One-shot migration: adds an empty Message_ID column to output/offres.csv
and appends "Message_ID" to config/config.json's offres_csv_headers.

Message_ID is appended at the END of the header list (not inserted), so
existing column letters (A..T) referenced by the Google Sheets conditional
formatting formulas stay unchanged.

Usage:
    python3 migrate_offres_add_message_id.py [--dry-run]
"""

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "config" / "config.json"
OFFRES_CSV = ROOT / "output" / "offres.csv"

NEW_COLUMN = "Message_ID"


def add_message_id_column(rows: list[dict], headers: list[str]) -> tuple[list[dict], list[str]]:
    """Return (rows, headers) with Message_ID appended if not already present."""
    if NEW_COLUMN in headers:
        return rows, headers
    new_headers = [*headers, NEW_COLUMN]
    new_rows = [{**row, NEW_COLUMN: ""} for row in rows]
    return new_rows, new_headers


def main(dry_run: bool) -> None:
    with CONFIG_FILE.open(encoding="utf-8") as f:
        config = json.load(f)
    headers = config["offres_csv_headers"]

    if OFFRES_CSV.exists():
        with OFFRES_CSV.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter=";"))
    else:
        rows = []

    new_rows, new_headers = add_message_id_column(rows, headers)

    print(f"{len(new_rows)} ligne(s) dans {OFFRES_CSV.name}")
    if new_headers == headers:
        print(f"{NEW_COLUMN} déjà présent, rien à faire.")
        return

    if dry_run:
        print(f"[DRY-RUN] Ajouterait la colonne {NEW_COLUMN} (position {len(new_headers)}).")
        return

    config["offres_csv_headers"] = new_headers
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.write("\n")

    if OFFRES_CSV.exists():
        with OFFRES_CSV.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=new_headers, delimiter=";")
            writer.writeheader()
            writer.writerows(new_rows)

    print(f"{CONFIG_FILE.name} et {OFFRES_CSV.name} mis à jour avec la colonne {NEW_COLUMN}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
