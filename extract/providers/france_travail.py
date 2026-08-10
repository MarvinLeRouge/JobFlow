import re

from extract.providers import offer_base
from extract.text import clean_entities, clean_html

FT_OFFER_RE = re.compile(
    r'<a href="(https://candidat\.francetravail\.fr/offres/recherche/detail/([A-Z0-9]+))\?[^"]*"[^>]*>\s*'
    r"<span[^>]*>\s*(.*?)\s*<br\s*/?>\s*(?:<!--.*?-->\s*)?"
    r"(.*?)</span>\s*</a>",
    re.S,
)
FT_SPAN_RE = re.compile(r"<span[^>]*>([^<]*)</span>")
FT_LOC_RE = re.compile(r"(\d{2})\s*-\s*(.+)")
FT_CONTRAT_RE = re.compile(r"\b(CDI|CDD|Alternance|Stage|Freelance|Intérim|Apprentissage)\b", re.I)


def extract_france_travail(html: str, msg, patterns: dict) -> list[dict]:
    """Chaque offre est un bloc <a href=".../detail/<ID>?..."> contenant le titre,
    puis (optionnellement) l'entreprise et toujours "Dept - Ville" dans des <span> imbriqués.
    Le type de contrat apparaît juste après, dans le tableau d'icônes."""
    offers = []
    seen_ids = set()

    for m in FT_OFFER_RE.finditer(html):
        url, offer_id, titre_html, loc_html = m.group(1), m.group(2), m.group(3), m.group(4)
        if offer_id in seen_ids:
            continue
        seen_ids.add(offer_id)

        o = offer_base()
        o["url"] = url
        o["url_qualite"] = "construite"
        o["notes"] = f"Offre n°{offer_id}"
        o["titre"] = clean_entities(re.sub(r"<[^>]+>", " ", titre_html)).strip()

        spans = [clean_entities(s).strip(" -") for s in FT_SPAN_RE.findall(loc_html)]
        loc_span = next((s for s in spans if FT_LOC_RE.match(s)), None)
        if loc_span:
            loc_m = FT_LOC_RE.match(loc_span)
            o["dept"] = loc_m.group(1)
            o["ville"] = loc_m.group(2).strip()
            autres = [s for s in spans if s is not loc_span]
            if autres:
                o["entreprise"] = autres[0]

        contrat_m = FT_CONTRAT_RE.search(clean_html(html[m.end() : m.end() + 600]))
        if contrat_m:
            o["type_contrat"] = contrat_m.group(1)

        if o["titre"] or o["entreprise"]:
            offers.append(o)

    return offers
