#!/usr/bin/env python3
"""Fetches new .eml alert emails from Gmail via the API, routes them into
sources/<provider>/, and records them in logs/email_ledger.json.

Usage:
    python3 fetch_gmail.py [--dry-run] [--since-days N]

--since-days is only needed for the very first run (no prior fetch history
in the ledger). Every subsequent run derives its start date automatically
from the most recent fetched_at in the ledger.
"""

import argparse
import base64
import email
import json
import re
from datetime import UTC, datetime, timedelta
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path

from googleapiclient.discovery import build

import auth
from ledger import load_ledger, save_ledger
from providers import expected_folder, load_domain_map, sender_domain

ROOT = Path(__file__).parent
SOURCES_DIR = ROOT / "sources"
LOGS_DIR = ROOT / "logs"
CONFIG_DIR = ROOT / "config"
PATTERNS_FILE = CONFIG_DIR / "scraping_patterns.json"
LEDGER_FILE = LOGS_DIR / "email_ledger.json"

OVERLAP_MARGIN = timedelta(hours=6)
IGNORED_GMAIL_IDS = {"before_gmail_api", "manual"}


def load_patterns() -> dict:
    with PATTERNS_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def collect_sender_domains(patterns: dict) -> list[str]:
    """Flatten sender_domains from every non-skip provider entry in
    scraping_patterns.json, deduplicated and sorted for stable query
    output. Digest-only entries (skip: true) are excluded, though in
    practice their domains are already covered by a sibling alert
    provider on the same domain."""
    domains = set()
    for key, p in patterns.items():
        if key.startswith("_") or p.get("skip"):
            continue
        domains.update(p.get("sender_domains", []))
    return sorted(domains)


def build_query(sender_domains: list[str], after_date: str) -> str:
    """Build a Gmail search query combining sender domains (OR'd via {})
    and an after: date filter."""
    if not sender_domains:
        raise ValueError("Aucun domaine expéditeur configuré (scraping_patterns.json)")
    senders = " ".join(f"from:{d}" for d in sender_domains)
    return f"({{{senders}}}) after:{after_date}"


def compute_after_date(last_fetch: datetime) -> str:
    """Gmail's after: filter is day-granularity; subtract a safety margin
    so a fetch late in the day still gets covered when re-run early the
    next day, without needing second-level precision."""
    return (last_fetch - OVERLAP_MARGIN).strftime("%Y/%m/%d")


def compute_last_fetch(ledger: dict) -> datetime | None:
    """Most recent fetched_at among real (API-sourced) ledger entries, or
    None if nothing has ever been fetched via the API yet."""
    timestamps = [
        e["fetched_at"]
        for e in ledger.values()
        if e.get("gmail_id") not in IGNORED_GMAIL_IDS and e.get("fetched_at")
    ]
    if not timestamps:
        return None
    latest = max(timestamps)
    return datetime.strptime(latest, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def determine_after_date(ledger: dict, since_days: int | None) -> str:
    last_fetch = compute_last_fetch(ledger)
    if last_fetch is not None:
        return compute_after_date(last_fetch)
    if since_days is not None:
        start = datetime.now(UTC) - timedelta(days=since_days)
        return start.strftime("%Y/%m/%d")
    raise ValueError(
        "Aucun fetch précédent dans le ledger et --since-days non fourni : "
        "impossible de déterminer un point de départ."
    )


def slugify_subject(subject: str, max_len: int = 40) -> str:
    """Turn an email subject into a filesystem-safe slug."""
    ascii_subject = subject.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_subject).strip("-").lower()
    return slug[:max_len] or "sans-sujet"


def build_filename(gmail_id: str, subject: str) -> str:
    """gmail_id guarantees uniqueness by construction: no collision
    detection needed even when two alerts share a near-identical subject."""
    return f"{gmail_id}-{slugify_subject(subject)}.eml"


def list_message_ids(service, query: str) -> list[str]:
    """Return all Gmail message IDs matching the query, paginating via
    nextPageToken (normal volume never needs a second page, but this
    avoids silently dropping messages after a long gap between runs)."""
    ids = []
    request = service.users().messages().list(userId="me", q=query)
    while request is not None:
        response = request.execute()
        ids.extend(m["id"] for m in response.get("messages", []))
        request = service.users().messages().list_next(request, response)
    return ids


def download_raw_eml(service, gmail_id: str) -> bytes:
    raw = service.users().messages().get(userId="me", id=gmail_id, format="raw").execute()["raw"]
    return base64.urlsafe_b64decode(raw)


def run(dry_run: bool, since_days: int | None = None) -> None:
    patterns = load_patterns()
    domain_map = load_domain_map(PATTERNS_FILE)
    sender_domains = collect_sender_domains(patterns)

    ledger = load_ledger(LEDGER_FILE)
    after_date = determine_after_date(ledger, since_days)
    query = build_query(sender_domains, after_date)

    print(f"{'[DRY-RUN] ' if dry_run else ''}Requête Gmail : {query}")

    service = build("gmail", "v1", credentials=auth.get_credentials())
    gmail_ids = list_message_ids(service, query)
    known_gmail_ids = {e.get("gmail_id") for e in ledger.values()}
    new_ids = [gid for gid in gmail_ids if gid not in known_gmail_ids]

    print(f"{len(gmail_ids)} message(s) trouvé(s), {len(new_ids)} nouveau(x)")

    downloaded = 0
    for gmail_id in new_ids:
        raw = download_raw_eml(service, gmail_id)
        msg = email.message_from_bytes(raw, policy=policy.default)
        message_id = (msg.get("Message-ID") or "").strip() or None

        if message_id is None:
            print(f"  SKIP (Message-ID introuvable) : {gmail_id}")
            continue
        if message_id in ledger:
            print(f"  SKIP (déjà connu sous un autre gmail_id) : {gmail_id}")
            continue

        domain = sender_domain(msg.get("From", ""))
        folder = expected_folder(domain, domain_map)
        if folder is None:
            print(f"  SKIP (domaine inconnu: {domain}) : {gmail_id}")
            continue

        filename = build_filename(gmail_id, msg.get("Subject", ""))
        dest_dir = SOURCES_DIR / folder
        dest_path = dest_dir / filename

        raw_date = msg.get("Date", "")
        dt = parsedate_to_datetime(raw_date) if raw_date else None
        date_email = dt.strftime("%Y-%m-%dT%H:%M:%S%z") if dt else ""

        print(f"  GET  {filename} → {folder}/")
        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(raw)
            now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            ledger[message_id] = {
                "gmail_id": gmail_id,
                "fichier": str(dest_path.relative_to(SOURCES_DIR)),
                "date_email": date_email,
                "fetched_at": now_str,
                "indexed_at": "",
                "statut_extraction": "PENDING",
            }
        downloaded += 1

    if not dry_run:
        save_ledger(LEDGER_FILE, ledger)

    print(f"\n{'Simulation' if dry_run else 'Résultat'} : {downloaded} email(s) téléchargé(s).")


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
    run(dry_run=args.dry_run, since_days=args.since_days)
