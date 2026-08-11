#!/usr/bin/env python3
"""Marks emails processed by the pipeline this run as read, applies the
"Recherche emploi" label, and archives them (removes INBOX) in Gmail.

Never deletes anything - see gmail_cleanup.py (manual, separate) for
moving already-labeled emails to Trash.

Usage: called by run_pipeline.py with the list of message_ids handled
during that run (ledger keys, not gmail_id).
"""

from pathlib import Path

from googleapiclient.discovery import build

import auth
from fetch_gmail import IGNORED_GMAIL_IDS
from ledger import load_ledger

ROOT = Path(__file__).parent
LEDGER_FILE = ROOT / "logs" / "email_ledger.json"

GMAIL_MODIFY_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_GMAIL_MODIFY_FILE = ROOT / "token_gmail_modify.json"

LABEL_NAME = "Recherche emploi"

# Only meant to cover one day's worth of processed emails (typically tens).
# A count this high signals a caller bug (e.g. passing the whole ledger
# instead of this run's delta) rather than a legitimate daily batch.
MAX_MESSAGES_PER_RUN = 200


def get_gmail_service():
    creds = auth.get_credentials(scopes=GMAIL_MODIFY_SCOPES, token_file=TOKEN_GMAIL_MODIFY_FILE)
    return build("gmail", "v1", credentials=creds)


def resolve_gmail_ids(ledger: dict, message_ids: list[str]) -> list[str]:
    """Real (non-sentinel) gmail_id values for the given ledger keys, in
    order, skipping keys absent from the ledger."""
    gmail_ids = []
    for mid in message_ids:
        entry = ledger.get(mid)
        if entry is None:
            continue
        gmail_id = entry.get("gmail_id")
        if gmail_id in IGNORED_GMAIL_IDS:
            continue
        gmail_ids.append(gmail_id)
    return gmail_ids


def get_or_create_label(service) -> str:
    result = service.users().labels().list(userId="me").execute()
    for label in result.get("labels", []):
        if label["name"] == LABEL_NAME:
            return label["id"]
    created = service.users().labels().create(userId="me", body={"name": LABEL_NAME}).execute()
    return created["id"]


def mark_processed(service, gmail_id: str, label_id: str) -> None:
    service.users().messages().modify(
        userId="me",
        id=gmail_id,
        body={"addLabelIds": [label_id], "removeLabelIds": ["UNREAD", "INBOX"]},
    ).execute()


def run(message_ids: list[str], dry_run: bool) -> None:
    if not message_ids:
        return

    ledger = load_ledger(LEDGER_FILE)
    gmail_ids = resolve_gmail_ids(ledger, message_ids)

    if not gmail_ids:
        return

    if len(gmail_ids) > MAX_MESSAGES_PER_RUN:
        raise RuntimeError(
            f"{len(gmail_ids)} emails a marquer, au-dela du plafond de securite "
            f"({MAX_MESSAGES_PER_RUN}) - execution stoppee, verifier la liste avant de continuer."
        )

    prefix = "[DRY-RUN] " if dry_run else ""
    print(f"{prefix}{len(gmail_ids)} email(s) a marquer traite(s) dans Gmail")
    if dry_run:
        return

    service = get_gmail_service()
    label_id = get_or_create_label(service)
    for gmail_id in gmail_ids:
        mark_processed(service, gmail_id, label_id)

    print(f"{len(gmail_ids)} email(s) marque(s) lu + label + archive(s)")
