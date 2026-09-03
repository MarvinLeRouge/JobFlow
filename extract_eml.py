#!/usr/bin/env python3
"""
extract_eml.py — Scraper principal : extrait les offres depuis les EML sources.

Usage : python3 extract_eml.py [--dry-run]

- Lit logs/email_ledger.json → fichiers à traiter (statut_extraction = PENDING)
- Détecte le provider     → config/scraping_patterns.json
- Extrait les offres      → output/import_YYYYMMDD.csv  (fichier daté par run)
- Dédup sur Cle_dedup     → Doublon_ID si doublon cross-provider
- Géocode les villes      → config/config.json + Nominatim (fallback)
- Journalise              → logs/YYYYMMDD-HHMM_extraction.log
                            logs/extraction_history.csv

Chaque run produit un fichier import_YYYYMMDD.csv autonome (avec en-tête),
contenant uniquement les nouvelles offres de ce run, lu ensuite par
sheets_sync.py pour la synchronisation automatique vers Google Sheets.

Le parsing par provider, le filtrage (dédup/blacklist/stack) et l'écriture
CSV/logs vivent dans le package extract/ ; ce fichier orchestre le run.
"""

import argparse
import email
import json
from datetime import datetime
from email import policy
from pathlib import Path
from zoneinfo import ZoneInfo

from extract.filters import blacklist_category, build_cle_dedup, extract_stack, is_blacklisted
from extract.geo import get_dept
from extract.io import (
    append_history,
    append_offres,
    ensure_offres_csv,
    load_dedup_map,
    write_run_log,
)
from extract.providers import EXTRACTORS, detect_provider
from ledger import load_ledger, save_ledger
from providers import sender_domain

# ── Chemins ───────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent
CONFIG_DIR = ROOT / "config"
LOGS_DIR = ROOT / "logs"
OUTPUT_DIR = ROOT / "output"
SOURCES_DIR = ROOT / "sources"

CONFIG_FILE = CONFIG_DIR / "config.json"
PATTERNS_FILE = CONFIG_DIR / "scraping_patterns.json"
LEDGER_FILE = LOGS_DIR / "email_ledger.json"
OFFRES_CSV = OUTPUT_DIR / "offres.csv"  # archive locale cumulative (référence dédup)
HISTORY_CSV = LOGS_DIR / "extraction_history.csv"

LOCAL_TZ = ZoneInfo("Europe/Paris")

# ── Chargement config ─────────────────────────────────────────────────────────


def load_config():
    with CONFIG_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def load_patterns():
    with PATTERNS_FILE.open(encoding="utf-8") as f:
        return json.load(f)


# ── Parsing EML ───────────────────────────────────────────────────────────────


def get_eml_parts(eml_path: Path):
    """Retourne (msg, html_body, text_body)."""
    with eml_path.open("rb") as f:
        msg = email.message_from_bytes(f.read(), policy=policy.default)
    html, text = "", ""
    for part in msg.walk():
        ct = part.get_content_type()
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        decoded = payload.decode(charset, errors="replace")
        if ct == "text/html" and not html:
            html = decoded
        elif ct == "text/plain" and not text:
            text = decoded
    return msg, html, text


# ── Main ──────────────────────────────────────────────────────────────────────


def resolve_write_headers(force_headers: bool | None) -> tuple[bool, str]:
    """
    force_headers :
      None  → automatique : toujours avec en-tête (chaque import_YYYYMMDD.csv
              est un fichier autonome, lu par sheets_sync.py)
      True  → forcer headers (--with-headers)
      False → forcer sans headers (--no-headers)
    """
    if force_headers is None:
        return True, "auto (toujours avec en-tête)"
    return force_headers, "forcé via --with-headers" if force_headers else "forcé via --no-headers"


def main(dry_run: bool, force_headers: bool | None = None):
    run_dt = datetime.now(LOCAL_TZ)
    log_path = LOGS_DIR / f"{run_dt.strftime('%Y%m%d-%H%M')}_extraction.log"
    log_entries: list[str] = []

    import_csv = None if dry_run else OUTPUT_DIR / f"import_{run_dt.strftime('%Y%m%d')}.csv"

    write_import_headers, headers_reason = resolve_write_headers(force_headers)

    def log(msg: str, level: str = "INFO"):
        prefix = {"INFO": "  ", "WARN": "⚠ ", "ERR ": "✗ ", "IGN ": "— "}
        log_entries.append(f"[{level}] {msg}")
        print(prefix.get(level, "  ") + msg)

    config = load_config()
    patterns = load_patterns()
    headers = config["offres_csv_headers"]
    keywords = config["stack_keywords"]
    blacklist = config.get("blacklist_titres", [])
    blacklist_categories = config.get("blacklist_categories", {})
    ville_dept = {k.lower(): v for k, v in config["ville_dept"].items()}

    ledger = load_ledger(LEDGER_FILE)
    pending = sorted(
        (
            mid
            for mid, entry in ledger.items()
            if entry.get("statut_extraction", "PENDING") == "PENDING"
        ),
        key=lambda mid: ledger[mid].get("date_email", ""),
    )

    if not pending:
        print("Aucun fichier EML en attente de traitement.")
        return

    dedup_map, max_e_id = load_dedup_map(OFFRES_CSV)
    ensure_offres_csv(OFFRES_CSV, import_csv, headers, write_import_headers)

    stats = {
        "fichiers_ok": 0,
        "fichiers_partiel": 0,
        "erreurs": 0,
        "ignores": 0,
        "offres_ecrites": 0,
        "doublons": 0,
        "blacklistes": 0,
        "dry_run": dry_run,
    }

    total = len(pending)
    headers_label = f"{'avec' if write_import_headers else 'sans'} en-tête ({headers_reason})"
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Traitement de {total} fichier(s) EML")
    if not dry_run and import_csv:
        print(f"  → {import_csv.name}  [{headers_label}]")
    print()

    for idx, message_id in enumerate(pending, 1):
        entry = ledger[message_id]
        rel_path = entry.get("fichier", "")
        eml_path = SOURCES_DIR / rel_path
        date_email = entry.get("date_email", "")[:10]

        pct = idx / total * 100
        print(f"[{idx}/{total} — {pct:.0f}%] {rel_path}")

        if not eml_path.exists():
            log(f"Fichier introuvable : {eml_path}", "ERR ")
            entry["statut_extraction"] = "ERREUR"
            stats["erreurs"] += 1
            continue

        try:
            msg, html, _text = get_eml_parts(eml_path)
        except Exception as e:
            log(f"Impossible de lire {rel_path} : {e}", "ERR ")
            entry["statut_extraction"] = "ERREUR"
            stats["erreurs"] += 1
            continue

        domain = sender_domain(msg.get("From", ""))
        provider_key, provider_cfg = detect_provider(domain, patterns)

        if provider_key is None:
            log(f"Provider inconnu (domaine: {domain}) — {rel_path}", "WARN")
            entry["statut_extraction"] = "ERREUR"
            stats["erreurs"] += 1
            continue

        if provider_cfg.get("skip"):
            log(f"EML ignoré [{provider_key}] : {rel_path}", "IGN ")
            entry["statut_extraction"] = "IGNORE"
            stats["ignores"] += 1
            continue

        extractor = EXTRACTORS.get(provider_key)
        if extractor is None:
            log(f"EML ignoré [pas d'extracteur pour {provider_key}] : {rel_path}", "IGN ")
            entry["statut_extraction"] = "IGNORE"
            stats["ignores"] += 1
            continue

        try:
            raw_offers = extractor(html, msg, provider_cfg)
        except Exception as e:
            log(f"Erreur d'extraction [{provider_key}] {rel_path} : {e}", "ERR ")
            entry["statut_extraction"] = "ERREUR"
            stats["erreurs"] += 1
            continue

        if not raw_offers:
            log(f"Aucune offre extraite [{provider_key}] : {rel_path}", "WARN")
            log(f"  → Sujet : {msg.get('Subject', '?')[:80]}", "WARN")
            entry["statut_extraction"] = "PARTIEL"
            stats["fichiers_partiel"] += 1
            continue

        source_display = {
            "france_travail": "France Travail",
            "indeed_alerte": "Indeed",
            "indeed_match": "Indeed",
            "linkedin": "LinkedIn",
            "meteojob_company": "Meteojob",
            "jobijoba_alerte": "Jobijoba",
            "talent_com": "Talent.com",
        }.get(provider_key, provider_key)

        new_rows = []
        offer_errors = 0

        for offer in raw_offers:
            if not offer.get("titre"):
                offer_errors += 1
                log(f"  Offre ignorée (titre vide) dans {rel_path}", "WARN")
                continue

            max_e_id += 1
            eid = f"E{max_e_id:06d}"

            if not offer.get("dept") and offer.get("ville"):
                offer["dept"] = get_dept(offer["ville"], ville_dept)

            search_text = offer["titre"] + " " + offer.get("notes", "")
            stack = extract_stack(search_text, keywords)

            cle = build_cle_dedup(
                offer.get("entreprise", ""),
                offer.get("ville", ""),
                offer["titre"],
            )

            doublon_id = ""
            if cle in dedup_map:
                doublon_id = dedup_map[cle]
                stats["doublons"] += 1
                log(f"  Doublon : {cle} → {doublon_id}", "INFO")
            else:
                dedup_map[cle] = eid

            notes = offer.get("notes", "")

            bl_term = is_blacklisted(offer["titre"], blacklist)
            if bl_term:
                stats["blacklistes"] += 1
                marker = f"⛔ Blacklisté: {bl_term}"
                notes = f"{notes} | {marker}" if notes else marker

            row = {
                "ID": eid,
                "Traite": "FALSE",
                "Date_decouverte": date_email,
                "Source": source_display,
                "Titre": offer["titre"],
                "Entreprise": offer.get("entreprise", ""),
                "Cle_dedup": cle,
                "Doublon_ID": doublon_id,
                "Ville": offer.get("ville", ""),
                "Dept": offer.get("dept", ""),
                "Type_contrat": offer.get("type_contrat", ""),
                "Salaire_min": offer.get("salaire_min", ""),
                "Salaire_max": offer.get("salaire_max", ""),
                "URL": offer.get("url", ""),
                "URL_qualite": offer.get("url_qualite", "vide"),
                "URL_redirect": "",
                "Stack": stack,
                "Raison_exclusion": (
                    f"Blacklisté: {blacklist_category(bl_term, blacklist_categories)}"
                    if bl_term
                    else ""
                ),
                "Date_candidature": "",
                "Notes": notes,
                "Message_ID": message_id,
            }
            new_rows.append(row)

        if new_rows and not dry_run:
            append_offres(OFFRES_CSV, import_csv, new_rows, headers)

        nb_ok = len(new_rows)
        nb_err = offer_errors
        stats["offres_ecrites"] += nb_ok

        statut = "OK" if nb_err == 0 else "PARTIEL"
        entry["statut_extraction"] = statut

        if statut == "OK":
            stats["fichiers_ok"] += 1
            log(f"  {nb_ok} offre(s) {'simulées' if dry_run else 'écrites'}", "INFO")
        else:
            stats["fichiers_partiel"] += 1
            log(f"  {nb_ok} offre(s) OK, {nb_err} ignorée(s)", "WARN")

    if not dry_run:
        save_ledger(LEDGER_FILE, ledger)

    print(f"\n{'=' * 55}")
    print(f"{'[DRY-RUN] ' if dry_run else ''}RAPPORT DE RUN — {run_dt.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'=' * 55}")
    print(f"  Fichiers traités  : {stats['fichiers_ok'] + stats['fichiers_partiel']}/{total}")
    print(f"  Offres écrites    : {stats['offres_ecrites']}")
    print(f"  Doublons détectés : {stats['doublons']}")
    print(f"  Blacklistés       : {stats['blacklistes']}")
    print(f"  Fichiers ignorés  : {stats['ignores']}")
    print(f"  Fichiers partiels : {stats['fichiers_partiel']}")
    print(f"  Erreurs           : {stats['erreurs']}")
    if stats["erreurs"] or stats["fichiers_partiel"]:
        print(f"\n  ⚠  Détails dans : {log_path.name}")
    if not dry_run and import_csv and stats["offres_ecrites"] > 0:
        print(f"\n  → Fichier prêt pour sheets_sync.py : {import_csv.name}")
    print(f"{'=' * 55}\n")

    if not dry_run:
        write_run_log(log_path, run_dt, log_entries, stats)
        append_history(HISTORY_CSV, run_dt, stats)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simule l'extraction sans écrire de fichiers"
    )
    hdr = parser.add_mutually_exclusive_group()
    hdr.add_argument(
        "--with-headers",
        action="store_true",
        help="Forcer la présence de l'en-tête dans le fichier import",
    )
    hdr.add_argument(
        "--no-headers",
        action="store_true",
        help="Forcer l'absence de l'en-tête dans le fichier import",
    )
    args = parser.parse_args()

    force_headers = None
    if args.with_headers:
        force_headers = True
    elif args.no_headers:
        force_headers = False

    main(dry_run=args.dry_run, force_headers=force_headers)
