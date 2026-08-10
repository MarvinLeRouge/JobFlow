import re

from extract.providers import offer_base
from extract.text import clean_html


def extract_indeed_match(html: str, msg, patterns: dict) -> list[dict]:
    subject = msg.get("Subject", "")
    # Subject : "TITRE – COMPANY" — seul le tiret cadratin (–, U+2013) sépare titre et
    # entreprise ; les tirets simples (-) et cadratins longs (—) peuvent apparaître dans
    # le titre lui-même (ex. "PHP - REACT (H/F) – Société"), d'où le split sur la
    # DERNIÈRE occurrence de " – ".
    text = clean_html(html)

    o = offer_base()
    subject_parts = subject.rsplit(" – ", 1)
    if len(subject_parts) == 2:
        o["titre"] = subject_parts[0].strip()
        o["entreprise"] = subject_parts[1].strip()

    # URL : premier lien cts.indeed.com
    url_m = re.search(r'href="(https://cts\.indeed\.com/v3/[^"]+)"', html)
    if url_m:
        o["url"] = url_m.group(1)
        o["url_qualite"] = "email"

    # Ville/dept : juste après le nom de l'entreprise dans le corps, sous l'une de
    # ces 3 formes ("STEP UP 83000 Toulon Salaire...", "... La Valette-du-Var (83)
    # Salaire...", "BlackPearl Télétravail Salaire..."). On cherche la bonne occurrence
    # de l'entreprise (elle apparaît aussi dans l'intro "Bonjour Jean...", sans lieu).
    if o["entreprise"]:
        for ent_m in re.finditer(re.escape(o["entreprise"]), text):
            seg = text[ent_m.end() : ent_m.end() + 160]
            loc_m = re.match(
                r"\s*(?:"
                r"(\d{5})\s+([A-ZÀ-Ÿ][\wà-ÿÀ-Ÿ'\-]*(?:[\s\-][\wà-ÿÀ-Ÿ'\-]+)*?)"
                r"(?=\s+(?:Salaire|Types? de postes?|Employeur réactif|Plusieurs postes))"
                r"|([A-ZÀ-Ÿ][^()]{1,40}?)\s*\((\d{2})\)"
                r"|(Télétravail)"
                r")",
                seg,
            )
            if loc_m:
                if loc_m.group(1):  # "83000 Toulon"
                    o["ville"] = loc_m.group(2).strip()
                    o["dept"] = loc_m.group(1)[:2]
                elif loc_m.group(3):  # "La Seyne-sur-Mer (83)"
                    o["ville"] = loc_m.group(3).strip()
                    o["dept"] = loc_m.group(4)
                else:  # "Télétravail"
                    o["ville"] = "Télétravail"
                break

    contrat_m = re.search(r"\b(CDI|CDD|Alternance|Stage|Freelance|Intérim)\b", text, re.I)
    if contrat_m:
        o["type_contrat"] = contrat_m.group(1)

    return [o] if o["titre"] else []
