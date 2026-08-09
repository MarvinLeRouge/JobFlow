#!/usr/bin/env python3
"""Runs the full pipeline: fetch_gmail -> rename_eml -> extract_eml.

Usage:
    python3 run_pipeline.py [--dry-run] [--since-days N]

--since-days is forwarded to fetch_gmail and is only needed for the very
first run, when the ledger holds no real fetch history yet (migrated
entries do not count as one).

Fail-fast: stops at the first step that raises. Later steps never run
against a state left inconsistent by an earlier failure.
"""

import argparse

import extract_eml
import fetch_gmail
import rename_eml
import sheets_sync


def run_pipeline(dry_run: bool, since_days: int | None = None) -> None:
    sheets_sync.check_error_gate()

    print("=== 1/4 - Fetch Gmail ===")
    fetch_gmail.run(dry_run=dry_run, since_days=since_days)

    print("\n=== 2/4 - Rename & index ===")
    rename_eml.run(dry_run=dry_run, purge=False)

    print("\n=== 3/4 - Extract offers ===")
    extract_eml.main(dry_run=dry_run)

    print("\n=== 4/4 - Sync to Google Sheets ===")
    sheets_sync.run(dry_run=dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="Point de départ pour le tout premier fetch (aucun historique en ledger)",
    )
    args = parser.parse_args()
    run_pipeline(dry_run=args.dry_run, since_days=args.since_days)
