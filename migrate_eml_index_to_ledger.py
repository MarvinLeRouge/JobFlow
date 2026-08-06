#!/usr/bin/env python3
"""One-shot migration: converts logs/eml_index.csv into logs/email_ledger.json.

Run once, after upgrading to the unified ledger. Does not delete the old
eml_index.csv — remove it manually once you've confirmed the migration.

Usage:
    python3 migrate_eml_index_to_ledger.py [--dry-run]
"""

import argparse
import csv
from pathlib import Path

from ledger import save_ledger

ROOT = Path(__file__).parent
LOGS_DIR = ROOT / "logs"
INDEX_CSV = LOGS_DIR / "eml_index.csv"
LEDGER_JSON = LOGS_DIR / "email_ledger.json"

BEFORE_GMAIL_API = "before_gmail_api"


def build_ledger_from_csv(csv_path: Path) -> dict:
    """Read the legacy eml_index.csv and return the equivalent ledger dict."""
    if not csv_path.exists():
        return {}
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    ledger = {}
    for row in rows:
        message_id = row["Message-ID"]
        indexed_at = row.get("Date_indexation", "")
        ledger[message_id] = {
            "gmail_id": BEFORE_GMAIL_API,
            "fichier": row.get("Fichier", ""),
            "date_email": row.get("Date_email", ""),
            "fetched_at": indexed_at,
            "indexed_at": indexed_at,
            "statut_extraction": row.get("Statut_extraction") or "PENDING",
        }
    return ledger


def main(dry_run: bool) -> None:
    ledger = build_ledger_from_csv(INDEX_CSV)
    print(f"{len(ledger)} entrée(s) migrée(s) depuis {INDEX_CSV.name}")
    if dry_run:
        print("[DRY-RUN] Rien écrit.")
        return
    if LEDGER_JSON.exists():
        print(f"ERREUR : {LEDGER_JSON} existe déjà, migration abandonnée.")
        raise SystemExit(1)
    save_ledger(LEDGER_JSON, ledger)
    print(f"Ledger écrit : {LEDGER_JSON}")
    print(f"NOTE : {INDEX_CSV} n'a pas été supprimé — à retirer manuellement une fois vérifié.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
