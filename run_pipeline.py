#!/usr/bin/env python3
"""Runs the full pipeline: fetch_gmail -> rename_eml -> extract_eml.

Usage:
    python3 run_pipeline.py [--dry-run]

Fail-fast: stops at the first step that raises. Later steps never run
against a state left inconsistent by an earlier failure.
"""

import argparse

import extract_eml
import fetch_gmail
import rename_eml


def run_pipeline(dry_run: bool) -> None:
    print("=== 1/3 - Fetch Gmail ===")
    fetch_gmail.run(dry_run=dry_run)

    print("\n=== 2/3 - Rename & index ===")
    rename_eml.run(dry_run=dry_run, purge=False)

    print("\n=== 3/3 - Extract offers ===")
    extract_eml.main(dry_run=dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_pipeline(dry_run=args.dry_run)
