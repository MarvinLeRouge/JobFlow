import re

from extract.providers import offer_base
from extract.text import clean_entities

# Chaque carte offre (gabarit "offre unique" ou "alerte multi-offres") démarre
# par un titre dans ce <div> précis - seul élément commun fiable aux deux
# gabarits. Les e-mails marketing (confirmation, relances "talent manager")
# n'ont aucun bloc de ce type : 0 match, donc 0 offre, sans entrée de config
# "skip" à maintenir séparément.
JOBLEADS_TITLE_RE = re.compile(
    r'color:\s*#100F0E;[^"]*font-size:\s*20px[^>]*>\s*(.*?)\s*</div>', re.S
)
# URL de l'offre : soit le lien englobant qui S'OUVRE AVANT le titre (gabarit
# "offre unique", où l'<a> couvre toute la carte), soit le lien CTA qui vient
# APRÈS le contenu (gabarit "alerte multi-offres"). On cherche après en
# priorité, puis avant - jamais les deux à la fois pour une même carte.
JOBLEADS_URL_RE = re.compile(r'href="(https://www\.jobleads\.com/(?:fr/)?job/[^"]+)"')
# L'identifiant hexadécimal stable de l'offre suit soit "/job/" (alerte),
# soit le dernier "--" du slug (offre unique) ; dans les deux cas il précède
# le "?" des paramètres de tracking (kuuid, utm_*, search_id...).
JOBLEADS_ID_RE = re.compile(r"(?:--|/job/)([a-f0-9]{20,40})(?:\?|$)")
# Lignes utiles (entreprise / lieu-mode / contrat-salaire) : un <div> dont le
# contenu textuel n'est pas une balise. La puce "•" ou "&bull;" est soit
# préfixée dans le même <div> que le texte (gabarit "offre unique"), soit
# dans son propre <div> vide de texte (gabarit "alerte") - dans ce dernier
# cas la capture est vide et la ligne est filtrée.
JOBLEADS_LINE_RE = re.compile(r"<div[^>]*>\s*(?:&bull;|•)?\s*([^<]{1,120}?)\s*</div>")
JOBLEADS_CONTRACT_TYPES = (
    "CDI",
    "CDD",
    "Alternance",
    "Stage",
    "Freelance",
    "Intérim",
    "Plein temps",
    "Temps partiel",
)
JOBLEADS_CONTRACT_RE = re.compile("|".join(re.escape(c) for c in JOBLEADS_CONTRACT_TYPES), re.I)
# Montant : devise suivie d'un nombre (espace fine insécable   entre
# milliers dans les e-mails réels) et, optionnellement, d'un second montant
# séparé par un tiret pour une fourchette.
JOBLEADS_SALARY_RE = re.compile(r"(?:EUR|USD|\$|€)\s*([\d\s ]{3,}?)(?:\s*-\s*([\d\s ]{3,}))?\s*$")

# Fenêtre pour les lignes utiles (entreprise/lieu/contrat-salaire) après le
# titre : celles-ci apparaissent toujours tôt dans la carte, pas besoin
# d'aller plus loin même pour la dernière carte d'un e-mail.
LINES_WINDOW = 2000


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def extract_jobleads(html: str, msg, patterns: dict) -> list[dict]:
    titles = list(JOBLEADS_TITLE_RE.finditer(html))
    offers = []

    for i, title_m in enumerate(titles):
        titre = clean_entities(title_m.group(1)).strip()
        if not titre:
            continue

        # Bornes exactes par le titre voisin plutôt qu'une fenêtre fixe en
        # caractères : une "Benefits Highlight Row" (A/B test, cf. commentaire
        # HTML réel) peut repousser le lien CTA très loin après le titre, et
        # le lien englobant du gabarit "offre unique" peut s'ouvrir très loin
        # avant - une fenêtre fixe a déjà raté l'URL des deux côtés en
        # production (voir tests de régression). Borner par le titre voisin
        # élimine aussi le risque de récupérer l'URL d'une carte adjacente.
        block_end = titles[i + 1].start() if i + 1 < len(titles) else len(html)
        block_start = titles[i - 1].end() if i > 0 else 0
        block_before = html[block_start : title_m.start()]
        block_after = html[title_m.end() : block_end]

        o = offer_base()
        o["titre"] = titre

        url_m = JOBLEADS_URL_RE.search(block_after) or JOBLEADS_URL_RE.search(block_before)
        if url_m:
            raw_url = clean_entities(url_m.group(1))
            id_m = JOBLEADS_ID_RE.search(raw_url)
            if id_m:
                o["url"] = f"https://www.jobleads.com/job/{id_m.group(1)}"
                o["url_qualite"] = "construite"
            else:
                o["url"] = raw_url
                o["url_qualite"] = "email"

        lines = [
            clean_entities(line).strip()
            for line in JOBLEADS_LINE_RE.findall(block_after[:LINES_WINDOW])
        ]
        lines = [line for line in lines if line]

        if lines:
            o["entreprise"] = lines[0]

        location_line = None
        contract_salary_line = None
        for line in lines[1:]:
            if "|" not in line:
                continue
            is_contract_or_salary = bool(
                JOBLEADS_SALARY_RE.search(line) or JOBLEADS_CONTRACT_RE.search(line)
            )
            if location_line is None and not is_contract_or_salary:
                location_line = line
            elif contract_salary_line is None and is_contract_or_salary:
                contract_salary_line = line
            if location_line and contract_salary_line:
                break

        if location_line:
            parts = [p.strip() for p in location_line.split("|")]
            o["ville"] = parts[0]
            if len(parts) > 1 and parts[1]:
                o["notes"] = f"Mode de travail : {parts[1]}"

        if contract_salary_line:
            for part in (p.strip() for p in contract_salary_line.split("|")):
                sal_m = JOBLEADS_SALARY_RE.search(part)
                if sal_m:
                    o["salaire_min"] = _digits(sal_m.group(1))
                    o["salaire_max"] = (
                        _digits(sal_m.group(2)) if sal_m.group(2) else o["salaire_min"]
                    )
                    continue
                contract_m = JOBLEADS_CONTRACT_RE.search(part)
                if contract_m:
                    o["type_contrat"] = contract_m.group(0)

        offers.append(o)

    return offers
