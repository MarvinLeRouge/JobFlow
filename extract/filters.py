"""Déduplication, blacklist de titres, et détection de stack technique."""

import re

from extract.text import normalize, strip_accents, titre_slug


def build_cle_dedup(entreprise: str, ville: str, titre: str) -> str:
    e = normalize(entreprise) or "inconnu"
    v = normalize(ville) or "inconnue"
    t = titre_slug(titre) or "inconnu"
    return f"{e}|{v}|{t}"


def is_blacklisted(titre: str, blacklist: list[str]) -> str | None:
    """Retourne le premier terme blacklisté trouvé dans le titre, ou None."""
    _APOS = re.compile(r"[‘’‚‛ʼ′]")

    def _norm(s: str) -> str:
        return _APOS.sub("'", strip_accents(s.lower()))

    titre_norm = _norm(titre)
    for term in blacklist:
        if _norm(term) in titre_norm:
            return term
    return None


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
