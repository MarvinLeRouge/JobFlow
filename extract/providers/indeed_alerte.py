import re

from extract.providers import offer_base
from extract.text import clean_entities, clean_html

INDEED_ALERTE_BLOCK_RE = re.compile(
    r'<h2[^>]*>\s*<a href="([^"]+)"[^>]*>\s*([^<]{3,120}?)\s*</a>\s*</h2>(.*?)(?=<h2[^>]*>|\Z)',
    re.S,
)
# Nom de l'entreprise et lieu : deux <td> consécutifs partageant le même style
# (couleur/taille/interligne), juste après le titre — la note (ex. <strong>4.7</strong>)
# est dans un <td> de taille différente et n'est donc pas captée.
INDEED_ALERTE_INFO_RE = re.compile(
    r'<td[^>]*style="[^"]*color:#2d2d2d;font-size:14px;line-height:21px[^"]*"[^>]*>\s*([^<]{1,100}?)\s*</td>',
    re.S,
)
INDEED_ALERTE_JK_RE = re.compile(r"jk=([a-f0-9]{16})")


def extract_indeed_alerte(html: str, msg, patterns: dict) -> list[dict]:
    """Chaque offre est un bloc <h2><a href="URL">TITRE</a></h2> suivi d'un tableau
    "Entreprise / note / lieu". Les liens pointent soit vers .../viewjob?jk=<id>
    soit vers des redirections .../pagead/clk/dl?... (sans jk) selon le modèle d'e-mail ;
    on normalise vers une URL viewjob courte quand un jk est présent, et on déduplique
    sur cet identifiant plutôt que sur l'URL complète (qui varie d'un envoi à l'autre)."""
    offers = []
    seen = set()
    for m in INDEED_ALERTE_BLOCK_RE.finditer(html):
        href, titre_raw, body = m.group(1), m.group(2), m.group(3)
        titre = clean_entities(titre_raw).strip()
        if len(titre) < 3:
            continue

        jk_m = INDEED_ALERTE_JK_RE.search(href)
        if jk_m:
            jk = jk_m.group(1)
            url = f"https://fr.indeed.com/viewjob?jk={jk}"
            url_qualite = "construite"
            dedup_key = jk
        else:
            url = clean_entities(href)
            url_qualite = "email"
            dedup_key = (titre, href)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        o = offer_base()
        o["titre"] = titre
        o["url"] = url
        o["url_qualite"] = url_qualite

        infos = INDEED_ALERTE_INFO_RE.findall(body[:1500])
        if len(infos) > 0:
            o["entreprise"] = clean_entities(infos[0]).strip()
        if len(infos) > 1:
            lieu = clean_entities(infos[1]).strip()
            city_m = re.match(r"(.+?)\s*\((\d{2})\)$", lieu)
            if city_m:
                o["ville"] = city_m.group(1).strip()
                o["dept"] = city_m.group(2)
            else:
                o["ville"] = lieu

        contrat_m = re.search(
            r"\b(CDI|CDD|Alternance|Stage|Freelance|Intérim)\b", clean_html(body[:1500]), re.I
        )
        if contrat_m:
            o["type_contrat"] = contrat_m.group(1)

        offers.append(o)
    return offers
