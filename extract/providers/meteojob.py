import re

from extract.providers import offer_base
from extract.text import clean_entities, clean_html


def extract_meteojob_company(html: str, msg, patterns: dict) -> list[dict]:
    subject = msg.get("Subject", "").strip()
    # Subject : "  COMPANY recrute un TITRE  "
    subj_m = re.match(r"^\s*(.+?)\s+recrute un\s+(.+?)\s*$", subject, re.I)

    o = offer_base()
    if subj_m:
        o["entreprise"] = subj_m.group(1).strip()
        o["titre"] = subj_m.group(2).strip()

    # URL de l'offre : lien CTA du modèle "Hot Offer" (https://www.meteojob.com/jobs/<id>?...),
    # avec repli sur l'ancienne URL canonique (slug + id) pour les anciens modèles d'e-mail.
    url_m = (
        re.search(
            r'<a[^>]*class="hotoffer-cta-link"[^>]*href="(https://www\.meteojob\.com/jobs/\d+\?[^"]{0,400})"',
            html,
            re.S,
        )
        or re.search(
            r'href="(https://www\.meteojob\.com/candidat/offres/offre-d-emploi-[^"]+)"', html
        )
        or re.search(r'href="(https://www\.meteojob\.com/jobs/\d+\?[^"]{0,400})"', html)
    )
    if url_m:
        o["url"] = clean_entities(url_m.group(1))
        o["url_qualite"] = "construite"

    # Ville + dept depuis le texte
    text = clean_html(html)
    city_m = re.search(r"\bVar\s*\((\d{2})\)|\b([A-ZÀ-Ÿ][a-zà-ÿ\s\-]+)\s*\((\d{2})\)", text)
    if city_m:
        if city_m.group(1):  # "Var (83)"
            o["dept"] = city_m.group(1)
        elif city_m.group(3):
            o["ville"] = city_m.group(2).strip()
            o["dept"] = city_m.group(3)

    contrat_m = re.search(r"\b(CDI|CDD|Alternance|Stage|Freelance|Intérim)\b", text, re.I)
    if contrat_m:
        o["type_contrat"] = contrat_m.group(1)

    return [o] if (o["titre"] or o["entreprise"]) else []
