#!/usr/bin/env python3
"""One-shot report (no write): lists the "ID | URL" of every JobLeads offer
whose URL is currently empty in output/offres.csv, by re-parsing the exact
.eml that produced it (resolved via its Message_ID in the ledger) with the
current extract_jobleads() - the window-boundary fix for the missing-URL
bug (see extract/providers/jobleads.py) only applies to future extractions,
this report is step one of deciding whether/how to backfill the rows it
affected.

Usage:
    python3 report_jobleads_missing_url.py
"""

import csv
from pathlib import Path

from extract.providers.jobleads import extract_jobleads
from extract_eml import get_eml_parts
from ledger import load_ledger

ROOT = Path(__file__).parent
OFFRES_CSV = ROOT / "output" / "offres.csv"
SOURCES_DIR = ROOT / "sources"
LEDGER_FILE = ROOT / "logs" / "email_ledger.json"


def find_offers_with_missing_url(offres_csv_path: Path) -> list[dict]:
    """JobLeads rows in output/offres.csv whose URL is empty."""
    with offres_csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    return [r for r in rows if r["Source"] == "JobLeads" and not r["URL"]]


def reextract_url(eml_path: Path, titre: str) -> str | None:
    """Re-parse the given .eml and return the URL of the offer matching
    `titre` exactly - a digest email holds several offers under one single
    Message_ID, so the row's own title is what disambiguates which one."""
    msg, html, _text = get_eml_parts(eml_path)
    for offer in extract_jobleads(html, msg, {}):
        if offer["titre"] == titre and offer["url"]:
            return offer["url"]
    return None


def run(
    offres_csv_path: Path = OFFRES_CSV,
    sources_dir: Path = SOURCES_DIR,
    ledger_file: Path = LEDGER_FILE,
) -> list[tuple[str, str | None]]:
    rows = find_offers_with_missing_url(offres_csv_path)
    ledger = load_ledger(ledger_file)

    results = []
    for row in rows:
        entry = ledger.get(row["Message_ID"])
        url = None
        if entry:
            eml_path = sources_dir / entry["fichier"]
            if eml_path.exists():
                url = reextract_url(eml_path, row["Titre"])
        results.append((row["ID"], url))
    return results


def main() -> None:
    results = run()
    if not results:
        print("Aucune offre JobLeads sans URL dans output/offres.csv.")
        return
    for offer_id, url in results:
        print(f"{offer_id} | {url or '(toujours introuvable)'}")


if __name__ == "__main__":
    main()
