"""Détection de provider et table de dispatch vers les extracteurs par provider."""


def offer_base() -> dict:
    return {
        "titre": "",
        "entreprise": "",
        "ville": "",
        "dept": "",
        "type_contrat": "",
        "salaire_min": "",
        "salaire_max": "",
        "url": "",
        "url_qualite": "vide",
        "notes": "",
    }


# Importés après offer_base() : chaque module provider fait `from extract.providers import
# offer_base`, ce qui exige que offer_base soit déjà défini dans ce module au moment
# de l'import (sinon ImportError sur module partiellement initialisé).
from extract.providers.france_travail import extract_france_travail  # noqa: E402
from extract.providers.indeed_alerte import extract_indeed_alerte  # noqa: E402
from extract.providers.indeed_match import extract_indeed_match  # noqa: E402
from extract.providers.jobijoba import extract_jobijoba  # noqa: E402
from extract.providers.linkedin import extract_linkedin  # noqa: E402
from extract.providers.meteojob import extract_meteojob_company  # noqa: E402
from extract.providers.talent_com import extract_talent_com  # noqa: E402


def detect_provider(domain: str, patterns: dict) -> tuple[str, dict] | tuple[None, None]:
    """Retourne (provider_key, provider_config) ou (None, None).

    Plusieurs providers peuvent déclarer un domaine suffixe commun
    (ex: indeed_alerte → indeed.com, indeed_match → match.indeed.com) ;
    on retient le domaine le plus spécifique (le plus de composants)."""
    parts = domain.split(".")
    best = None
    best_specificity = 0
    for key, p in patterns.items():
        if key.startswith("_"):
            continue
        for d in p.get("sender_domains", []):
            d_parts = d.lower().split(".")
            if parts[-len(d_parts) :] == d_parts and len(d_parts) > best_specificity:
                best = (key, p)
                best_specificity = len(d_parts)
    return best if best else (None, None)


# Dispatch table
EXTRACTORS = {
    "france_travail": extract_france_travail,
    "indeed_alerte": extract_indeed_alerte,
    "indeed_match": extract_indeed_match,
    "linkedin": extract_linkedin,
    "meteojob_company": extract_meteojob_company,
    "meteojob_digest": None,  # skip
    "jobijoba_alerte": extract_jobijoba,
    "jobijoba_digest": None,  # skip
    "talent_com": extract_talent_com,
    "hellowork": None,  # patterns à définir
}
