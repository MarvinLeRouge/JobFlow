"""Déduplication, blacklist de titres, et détection de stack technique."""

import re

from extract.text import normalize, strip_accents, titre_slug


def build_cle_dedup(entreprise: str, ville: str, titre: str, row_id: str) -> str:
    """Construit la clé de dédup. Un champ vide est remplacé par row_id (et non par un
    placeholder générique) pour éviter les fausses collisions entre offres distinctes."""
    e = normalize(entreprise) or row_id
    v = normalize(ville) or row_id
    t = titre_slug(titre) or row_id
    return f"{e}|{v}|{t}"


_APOS = re.compile(r"[‘’‚‛ʼ′]")


def _titre_contains_any(titre: str, terms: list[str]) -> str | None:
    """Retourne le premier terme trouvé dans le titre (recherche insensible à la
    casse et aux accents), ou None."""

    def _norm(s: str) -> str:
        return _APOS.sub("'", strip_accents(s.lower()))

    titre_norm = _norm(titre)
    for term in terms:
        if _norm(term) in titre_norm:
            return term
    return None


def is_blacklisted(titre: str, blacklist: list[str]) -> str | None:
    """Retourne le premier terme blacklisté trouvé dans le titre, ou None."""
    return _titre_contains_any(titre, blacklist)


def is_stage_alternance(titre: str, terms: list[str]) -> str | None:
    """Retourne le premier terme stage/alternance trouvé dans le titre, ou None."""
    return _titre_contains_any(titre, terms)


def is_hors_stack(stack: str, excluded_tags: list[str]) -> bool:
    """True si le Stack détecté (tags séparés par des virgules) contient un des tags exclus."""
    tags = set(stack.split(",")) if stack else set()
    return bool(tags & set(excluded_tags))


# Motif Jobijoba repéré comme offre bidon (agrégateur qui renvoie vers une liste
# plutôt qu'une offre réelle) : titre se terminant par un montant arrondi à 2
# chiffres suivi de ".000 Par An" - sensible à la casse ("Par An" exact), car
# c'est précisément le gabarit Jobijoba a produit pour ces offres.
JOBIJOBA_FAKE_SALARY_RE = re.compile(r"€\d{2}\.0{3} Par An$")


def is_jobijoba_fake_salary_listing(titre: str) -> bool:
    """True si le titre Jobijoba correspond au motif d'offre bidon connu."""
    return bool(JOBIJOBA_FAKE_SALARY_RE.search(titre))


def extract_stack(text: str, keywords: dict) -> str:
    """Retourne les tags tech trouvés dans le texte, séparés par virgules."""
    text_lower = text.lower()
    found = []
    for canonical, variations in keywords.items():
        for v in variations:
            pattern = r"(?<![a-zA-Z0-9])" + re.escape(v) + r"(?![a-zA-Z0-9])"
            if re.search(pattern, text_lower):
                found.append(canonical)
                break
    return ",".join(found)
