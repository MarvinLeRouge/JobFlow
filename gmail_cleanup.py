#!/usr/bin/env python3
"""Manually-triggered cleanup: moves already-labeled ("Recherche emploi")
emails to Gmail's Trash - but only those the local ledger confirms this
pipeline actually processed. Never trusts the Gmail label alone, since
the user may apply it by hand to unrelated emails.

Trash, not permanent deletion: Gmail keeps trashed messages for 30 days
before purging them, and an already-trashed message drops out of the
label search on the next run (Gmail excludes Trash from list results by
default), so this script is naturally idempotent without needing its own
state tracking.

Never wired into run_pipeline.py or login_pipeline_check.py - run by
hand only.

Usage:
    python3 gmail_cleanup.py --dry-run
    python3 gmail_cleanup.py
"""

import argparse
from pathlib import Path

from fetch_gmail import IGNORED_GMAIL_IDS
from gmail_labeling import LABEL_NAME, get_gmail_service, get_or_create_label
from ledger import load_ledger

ROOT = Path(__file__).parent
LEDGER_FILE = ROOT / "logs" / "email_ledger.json"


def known_processed_gmail_ids(ledger: dict) -> set[str]:
    """Real (non-sentinel) gmail_id values for ledger entries the pipeline
    actually processed. ERREUR entries are excluded on purpose: extraction
    genuinely failed for them, nothing reliable was captured elsewhere, so
    they should stay visible (labeled, archived) until resolved by hand
    rather than being auto-trashed."""
    ids = set()
    for entry in ledger.values():
        gmail_id = entry.get("gmail_id")
        if gmail_id in IGNORED_GMAIL_IDS:
            continue
        if entry.get("statut_extraction") in (None, "PENDING", "ERREUR"):
            continue
        ids.add(gmail_id)
    return ids


def list_labeled_message_ids(service, label_id: str) -> list[str]:
    ids = []
    request = service.users().messages().list(userId="me", labelIds=[label_id])
    while request is not None:
        response = request.execute()
        ids.extend(m["id"] for m in response.get("messages", []))
        request = service.users().messages().list_next(request, response)
    return ids


def trash_message(service, gmail_id: str) -> None:
    service.users().messages().trash(userId="me", id=gmail_id).execute()


def run(dry_run: bool) -> None:
    ledger = load_ledger(LEDGER_FILE)
    known_ids = known_processed_gmail_ids(ledger)

    service = get_gmail_service()
    label_id = get_or_create_label(service)
    labeled_ids = list_labeled_message_ids(service, label_id)

    to_trash = [gid for gid in labeled_ids if gid in known_ids]
    skipped = len(labeled_ids) - len(to_trash)

    prefix = "[DRY-RUN] " if dry_run else ""
    print(f"{prefix}{len(labeled_ids)} email(s) portent le label {LABEL_NAME!r}")
    print(f"{prefix}{len(to_trash)} confirme(s) traite(s) par le pipeline -> corbeille")
    if skipped:
        print(f"{prefix}{skipped} ignore(s) (label present mais pas reconnu par le ledger)")

    if dry_run or not to_trash:
        return

    for gmail_id in to_trash:
        trash_message(service, gmail_id)

    print(f"{len(to_trash)} email(s) mis a la corbeille")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
