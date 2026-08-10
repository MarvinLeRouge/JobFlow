"""Écriture de l'archive offres.csv, du fichier d'import daté, et des logs de run."""

import csv
from datetime import datetime
from pathlib import Path


def load_dedup_map(offres_csv: Path) -> tuple[dict, int]:
    """Retourne ({cle_dedup: id}, max_e_number) depuis offres.csv."""
    dedup = {}
    max_e = 0
    if not offres_csv.exists():
        return dedup, max_e
    with offres_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            cle = row.get("Cle_dedup", "")
            rid = row.get("ID", "")
            if cle:
                dedup[cle] = rid
            if rid.startswith("E"):
                try:
                    max_e = max(max_e, int(rid[1:]))
                except ValueError:
                    pass
    return dedup, max_e


def ensure_offres_csv(
    offres_csv: Path, import_csv: Path | None, headers: list, write_import_headers: bool
):
    offres_csv.parent.mkdir(parents=True, exist_ok=True)
    if not offres_csv.exists():
        with offres_csv.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f, delimiter=";").writerow(headers)
    # Créer le fichier d'import du run
    if import_csv and not import_csv.exists():
        with import_csv.open("w", newline="", encoding="utf-8") as f:
            if write_import_headers:
                csv.writer(f, delimiter=";").writerow(headers)
            # sinon fichier vide — les données seront appendées sans en-tête


def append_offres(offres_csv: Path, import_csv: Path | None, rows: list[dict], headers: list):
    # Archive locale cumulative (pour la déduplication)
    with offres_csv.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
        writer.writerows(rows)
    # Fichier d'import daté (nouvelles lignes du run → à importer dans Sheets)
    if import_csv:
        with import_csv.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
            writer.writerows(rows)


def write_run_log(log_path: Path, run_dt: datetime, entries: list[str], stats: dict):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        f.write(f"=== Extraction EML — {run_dt.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
        for line in entries:
            f.write(line + "\n")
        f.write("\n--- RÉSUMÉ ---\n")
        for k, v in stats.items():
            f.write(f"  {k}: {v}\n")


def append_history(history_csv: Path, run_dt: datetime, stats: dict):
    history_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "Date_run",
        "Fichiers_traites",
        "Offres_extraites",
        "Doublons",
        "Ignores",
        "Erreurs",
        "Dry_run",
    ]
    exists = history_csv.exists()
    with history_csv.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "Date_run": run_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "Fichiers_traites": stats.get("fichiers_ok", 0),
                "Offres_extraites": stats.get("offres_ecrites", 0),
                "Doublons": stats.get("doublons", 0),
                "Ignores": stats.get("ignores", 0),
                "Erreurs": stats.get("erreurs", 0),
                "Dry_run": stats.get("dry_run", False),
            }
        )
