import re

from extract.providers import offer_base
from extract.text import clean_entities, clean_html

# Repère chaque offre via son attribut title="TITRE - PLATEFORME" : la plateforme
# source est un identifiant sans espace (ex. "hellowork.com", "adzuna_dynamic_fr_low",
# "RégionsJob"...) dont le format varie beaucoup et ne suit pas toujours un schéma de
# domaine — d'où le ".+?" gourmand côté titre, qui laisse la plateforme capter le
# dernier token avant le guillemet fermant, même quand le titre contient lui-même " - ".
JOBIJOBA_TITLE_RE = re.compile(r'title="(.+?) - ([^"\s]+)"')
# Ville : premier <span> texte suivant la fermeture </strong> du titre.
JOBIJOBA_VILLE_RE = re.compile(r"</strong>.*?<span>\s*([^<]{2,50}?)\s*</span>", re.S)


def extract_jobijoba(html: str, msg, patterns: dict) -> list[dict]:
    offers = []
    title_matches = list(JOBIJOBA_TITLE_RE.finditer(html))

    for i, title_m in enumerate(title_matches):
        titre = clean_entities(title_m.group(1)).strip()
        source_platform = title_m.group(2).strip()
        if len(titre) < 4:
            continue

        block_end = title_matches[i + 1].start() if i + 1 < len(title_matches) else len(html)
        block = html[title_m.start() : block_end]

        o = offer_base()
        o["titre"] = titre

        # URL de redirection jobijoba : la carte de l'offre est tout entière le
        # <a href="clic/.../N/...">, qui s'OUVRE AVANT le titre (le title="..."
        # est dans un <span> imbriqué ~600 caractères plus loin). Chercher en
        # avant depuis le titre récupère donc le lien clic de l'offre SUIVANTE
        # (décalage d'un cran) — on cherche ici le dernier lien clic/ rencontré
        # AVANT le titre, qui correspond à l'ouverture de SA propre carte.
        url_m = None
        for cm in re.finditer(
            r'<a[^>]*href="(https://emails\.jobijoba\.com/clic/[^"]+)"', html[: title_m.start()]
        ):
            url_m = cm
        if url_m:
            o["url"] = url_m.group(1)
            o["url_qualite"] = "email"

        text_block = clean_html(block[:1500])

        # Entreprise (premier span color:#000000) : absent pour les annonces
        # relayées depuis d'autres jobboards (hellowork...) qui ne le communiquent pas.
        company_m = re.search(r"color:#000000[^>]*>([^<]{2,60})</span>", block)
        if company_m:
            o["entreprise"] = clean_entities(company_m.group(1)).strip()

        # Ville : clean_html() aplatit les retours à la ligne, donc une recherche par
        # lignes ne fonctionne pas — on cible directement le <span> dans le HTML brut.
        ville_m = JOBIJOBA_VILLE_RE.search(block[:1000])
        if ville_m:
            o["ville"] = clean_entities(ville_m.group(1)).strip()

        # Salaire min/max depuis HTML brut (spans salaryCurrency imbriqués)
        sal_m = re.search(
            r"(\d[\d\s]+)\s*<span itemprop=['\"]salaryCurrency['\"]>€</span>\s*à\s*"
            r"(\d[\d\s]+)\s*<span itemprop=['\"]salaryCurrency['\"]>€</span>\s*(par an|par mois)",
            block,
        )
        if sal_m:
            factor = 12 if sal_m.group(3) == "par mois" else 1
            try:
                o["salaire_min"] = str(int(re.sub(r"\s", "", sal_m.group(1))) * factor)
                o["salaire_max"] = str(int(re.sub(r"\s", "", sal_m.group(2))) * factor)
            except ValueError:
                pass

        contrat_m = re.search(
            r"\b(CDI|CDD|Alternance|Stage|Freelance|Indépendant|Intérim)\b", text_block, re.I
        )
        if contrat_m:
            o["type_contrat"] = contrat_m.group(1)

        if source_platform and source_platform not in ("jobijoba.com",):
            o["notes"] = f"Via Jobijoba ({source_platform})"

        offers.append(o)
    return offers
