#!/usr/bin/env python3
"""
Renomme les fichiers .eml dans sources/, dédoublonne via un index Message-ID,
et vérifie que chaque fichier est dans le bon dossier provider.

Utilisation :
    python3 rename_eml.py [--dry-run] [--purge] [--check]

--dry-run : affiche les actions sans les effectuer.
--purge   : vide le dossier sources/_duplicates/ (après vérification manuelle).
--check   : vérifie que chaque .eml est dans le bon dossier provider (lecture seule).

Comportement (sans --check) :
  1. Lit l'index logs/eml_index.csv (Message-ID déjà vus).
  2. Pour chaque .eml dans sources/ (récursif, hors _duplicates/ et tests/) :
     - Message-ID déjà dans l'index → déplacé dans sources/_duplicates/
     - Message-ID absent, fichier déjà préfixé yyyymmdd-hhmm- → ajouté à l'index, ignoré
     - Message-ID absent, fichier non préfixé → renommé, ajouté à l'index
  3. Met à jour logs/eml_index.csv.
"""

import argparse
import csv
import email
import re
import shutil
import sys
from datetime import UTC, datetime
from email import policy
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from providers import expected_folder, load_domain_map, sender_domain

SOURCES_DIR = Path(__file__).parent / "sources"
LOGS_DIR = Path(__file__).parent / "logs"
CONFIG_DIR = Path(__file__).parent / "config"
INDEX_FILE = LOGS_DIR / "eml_index.csv"
PATTERNS_FILE = CONFIG_DIR / "scraping_patterns.json"
DUPES_DIR = SOURCES_DIR / "_duplicates"
TESTS_DIR = SOURCES_DIR / "tests"
LOCAL_TZ = ZoneInfo("Europe/Paris")
DATE_PREFIX_RE = re.compile(r"^\d{8}-\d{4}-")
INDEX_FIELDS = ["Message-ID", "Fichier", "Date_email", "Date_indexation", "Statut_extraction"]


# ── Check ─────────────────────────────────────────────────────────────────────


def check_folders():
    """Vérifie que chaque EML est dans le bon dossier provider. Lecture seule."""
    domain_map = load_domain_map(PATTERNS_FILE)
    if not domain_map:
        print("Aucun mapping domaine→dossier trouvé dans scraping_patterns.json.", file=sys.stderr)
        return

    eml_files = sorted(
        f
        for f in SOURCES_DIR.rglob("*.eml")
        if DUPES_DIR not in f.parents and TESTS_DIR not in f.parents
    )

    if not eml_files:
        print("Aucun fichier .eml trouvé dans sources/ (hors _duplicates/ et tests/).")
        return

    ok = mismatches = unknown = 0
    mismatch_list = []
    unknown_list = []

    for eml_path in eml_files:
        actual_folder = eml_path.parent.name
        try:
            with eml_path.open("rb") as f:
                msg = email.message_from_bytes(f.read(), policy=policy.default)
            from_hdr = msg.get("From", "")
        except Exception as e:
            print(f"  ERREUR lecture ({eml_path.name}): {e}", file=sys.stderr)
            continue

        domain = sender_domain(from_hdr)
        exp_fld = expected_folder(domain, domain_map)

        if exp_fld is None:
            unknown += 1
            unknown_list.append((str(eml_path.relative_to(SOURCES_DIR)), from_hdr, domain))
        elif exp_fld == actual_folder:
            ok += 1
        else:
            mismatches += 1
            mismatch_list.append(
                (
                    str(eml_path.relative_to(SOURCES_DIR)),
                    actual_folder,
                    exp_fld,
                    domain,
                )
            )

    print(f"Vérification de {len(eml_files)} fichier(s)\n")

    if mismatches:
        print(f"── MAUVAIS DOSSIER ({mismatches}) ──────────────────────────────")
        for rel, actual, expected, dom in mismatch_list:
            print(f"  {rel}")
            print(f"    dossier actuel : {actual}/")
            print(f"    dossier attendu: {expected}/  (domaine: {dom})")
    else:
        print("── Aucun fichier mal placé ✓")

    if unknown:
        print(f"\n── PROVIDER INCONNU ({unknown}) ─────────────────────────────────")
        for rel, from_hdr, dom in unknown_list:
            print(f"  {rel}")
            print(f"    From: {from_hdr[:80]}  (domaine: {dom})")
        print("  → Ajouter ces domaines dans config/scraping_patterns.json")

    print(f"\nRésultat : {ok} OK, {mismatches} mal placé(s), {unknown} provider inconnu(s).")


# ── Index helpers ─────────────────────────────────────────────────────────────


def load_index() -> dict:
    """Retourne un dict {message_id: row} depuis eml_index.csv.
    Ajoute Statut_extraction = PENDING si la colonne est absente (migration)."""
    if not INDEX_FILE.exists():
        return {}
    with INDEX_FILE.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    result = {}
    for row in rows:
        if "Statut_extraction" not in row:
            row["Statut_extraction"] = "PENDING"
        result[row["Message-ID"]] = row
    return result


def save_index(index: dict):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with INDEX_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows(index.values())


# ── EML helpers ───────────────────────────────────────────────────────────────


def parse_headers(eml_path: Path):
    """Retourne (message_id, datetime) depuis les headers de l'EML, ou (None, None)."""
    try:
        with eml_path.open("rb") as f:
            msg = email.message_from_bytes(f.read(), policy=policy.default)
        mid = msg.get("Message-ID", "").strip()
        raw_date = msg.get("Date", "")
        dt = parsedate_to_datetime(raw_date).astimezone(LOCAL_TZ) if raw_date else None
        return (mid or None, dt)
    except Exception as e:
        print(f"  ERREUR lecture ({eml_path.name}): {e}", file=sys.stderr)
        return (None, None)


def build_new_name(dt, stem: str) -> str:
    return f"{dt.strftime('%Y%m%d-%H%M')}-{stem}.eml"


def resolve_collision(base_path: Path, dt, stem: str) -> Path:
    new_path = base_path.parent / build_new_name(dt, stem)
    counter = 2
    while new_path.exists():
        new_path = base_path.parent / f"{dt.strftime('%Y%m%d-%H%M')}-{stem}_{counter}.eml"
        counter += 1
    return new_path


# ── Main ──────────────────────────────────────────────────────────────────────


def run(dry_run: bool, purge: bool):
    if purge:
        if not DUPES_DIR.exists() or not any(DUPES_DIR.iterdir()):
            print("sources/_duplicates/ est vide ou absent — rien à purger.")
            return
        files = sorted(DUPES_DIR.iterdir())
        print(
            f"{'[DRY-RUN] ' if dry_run else ''}Purge de {len(files)} fichier(s) dans _duplicates/"
        )
        for f in files:
            print(f"  DEL {f.name}")
            if not dry_run:
                f.unlink()
        if not dry_run:
            print("Purge terminée.")
        return

    eml_files = sorted(
        f
        for f in SOURCES_DIR.rglob("*.eml")
        if DUPES_DIR not in f.parents and TESTS_DIR not in f.parents
    )

    if not eml_files:
        print("Aucun fichier .eml trouvé dans sources/ (hors _duplicates/).")
        return

    tag = "[DRY-RUN] " if dry_run else ""
    print(f"{tag}{len(eml_files)} fichier(s) .eml trouvé(s)\n")

    index = load_index()
    now_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    renamed = duped = skipped = errors = 0

    for eml_path in eml_files:
        rel = eml_path.relative_to(SOURCES_DIR)
        mid, dt = parse_headers(eml_path)

        if mid is None:
            print(f"  SKIP (Message-ID introuvable) : {rel}")
            errors += 1
            continue

        # ── Doublon ───────────────────────────────────────────────────────────
        if mid in index:
            stored = index[mid].get("Fichier", "")
            if stored == str(rel):
                # Même fichier, déjà indexé → rien à faire
                skipped += 1
                continue
            # Message-ID connu mais chemin différent → vrai doublon
            DUPES_DIR.mkdir(parents=True, exist_ok=True)
            dest = DUPES_DIR / eml_path.name
            counter = 2
            while dest.exists():
                dest = DUPES_DIR / f"{eml_path.stem}_{counter}.eml"
                counter += 1
            print(f"  DUP  {rel}\n       → _duplicates/{dest.name}")
            print(f"       (déjà indexé comme : {stored})")
            if not dry_run:
                shutil.move(str(eml_path), dest)
            duped += 1
            continue

        date_str = dt.strftime("%Y-%m-%dT%H:%M:%S%z") if dt else ""

        # ── Déjà préfixé : indexer sans renommer ─────────────────────────────
        if DATE_PREFIX_RE.match(eml_path.name):
            print(f"  IDX  (déjà préfixé) : {rel}")
            if not dry_run:
                index[mid] = {
                    "Message-ID": mid,
                    "Fichier": str(rel),
                    "Date_email": date_str,
                    "Date_indexation": now_str,
                    "Statut_extraction": "PENDING",
                }
            skipped += 1
            continue

        # ── Renommer et indexer ───────────────────────────────────────────────
        if dt is None:
            print(f"  SKIP (date introuvable) : {rel}")
            errors += 1
            continue

        new_path = resolve_collision(eml_path, dt, eml_path.stem)
        rel_new = new_path.relative_to(SOURCES_DIR)
        print(f"  REN  {rel}\n       → {rel_new}")

        if not dry_run:
            eml_path.rename(new_path)
            index[mid] = {
                "Message-ID": mid,
                "Fichier": str(rel_new),
                "Date_email": date_str,
                "Date_indexation": now_str,
                "Statut_extraction": "PENDING",
            }
        renamed += 1

    if not dry_run:
        save_index(index)
        print(f"\nIndex mis à jour : {len(index)} entrée(s) → {INDEX_FILE}")

    print(
        f"\n{'Simulation' if dry_run else 'Résultat'} : "
        f"{renamed} renommé(s), {duped} doublon(s) → _duplicates/, "
        f"{skipped} déjà préfixés, {errors} erreur(s)."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Affiche les actions sans les effectuer"
    )
    parser.add_argument(
        "--purge", action="store_true", help="Vide sources/_duplicates/ après vérification manuelle"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Vérifie que chaque .eml est dans le bon dossier provider (lecture seule)",
    )
    args = parser.parse_args()

    if args.check:
        check_folders()
    else:
        run(dry_run=args.dry_run, purge=args.purge)
