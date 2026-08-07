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
import os
import re
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG_FILE = ROOT / "config" / "config.json"
OFFRES_CSV = ROOT / "output" / "offres.csv"

NEW_COLUMN = "Message_ID"
HEADERS_KEY = "offres_csv_headers"


def add_message_id_column(rows: list[dict], headers: list[str]) -> tuple[list[dict], list[str]]:
    """Return (rows, headers) with Message_ID appended if not already present.

    A row that already carries a Message_ID value keeps it, so re-running
    the migration over a CSV that was already converted is harmless."""
    if NEW_COLUMN in headers:
        return rows, headers
    new_headers = [*headers, NEW_COLUMN]
    new_rows = [{**row, NEW_COLUMN: row.get(NEW_COLUMN) or ""} for row in rows]
    return new_rows, new_headers


def find_array_close(text: str, start: int) -> int:
    """Index of the ] closing the array opened just before start, ignoring
    any bracket that sits inside a JSON string literal."""
    depth = 1
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        char = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("Tableau JSON non terminé dans le fichier de configuration.")


def insert_before_array_close(text: str, array_key: str, new_item: str) -> str:
    """Append new_item as the last string element of the JSON array bound to
    array_key, by editing the raw text.

    A json.load/json.dump round-trip would reformat the whole file and turn a
    one-word addition into a few hundred lines of diff, so the insertion is
    done in place and every other byte of the file is left untouched."""
    match = re.search(rf'"{re.escape(array_key)}"\s*:\s*\[', text)
    if match is None:
        raise ValueError(f"Clé {array_key} introuvable (ou non suivie d'un tableau).")

    open_end = match.end()
    close = find_array_close(text, open_end)

    # Insert right after the last element rather than right before the ],
    # which is usually preceded by a newline and indentation.
    insert_at = close
    while insert_at > open_end and text[insert_at - 1].isspace():
        insert_at -= 1

    item = json.dumps(new_item, ensure_ascii=False)
    prefix = ", " if insert_at > open_end else ""
    return f"{text[:insert_at]}{prefix}{item}{text[insert_at:]}"


def write_text_atomic(path: Path, text: str) -> None:
    """Write text through a temp file in the same directory, then move it
    onto path in one atomic step, so the existing file is never truncated
    by a write that fails partway."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def write_csv_atomic(path: Path, rows: list[dict], headers: list[str]) -> None:
    """Same atomic temp-file-then-replace pattern as write_text_atomic, for
    the semicolon-separated offres.csv."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def main(dry_run: bool) -> None:
    with CONFIG_FILE.open(encoding="utf-8") as f:
        config = json.load(f)
    headers = config[HEADERS_KEY]

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

    # offres.csv first, config.json second: if the process dies between the
    # two, the CSV already holds the new column while config.json does not
    # claim it yet, so re-running the migration retries the config step.
    if OFFRES_CSV.exists():
        write_csv_atomic(OFFRES_CSV, new_rows, new_headers)

    config_text = CONFIG_FILE.read_text(encoding="utf-8")
    new_config_text = insert_before_array_close(config_text, HEADERS_KEY, NEW_COLUMN)
    json.loads(new_config_text)  # fail before touching the real file
    write_text_atomic(CONFIG_FILE, new_config_text)

    print(f"{CONFIG_FILE.name} et {OFFRES_CSV.name} mis à jour avec la colonne {NEW_COLUMN}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
