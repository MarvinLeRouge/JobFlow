import re

from extract.providers import offer_base
from extract.text import clean_entities

# Liens de pied de page Talent.com captés à tort comme titres d'offres
TALENT_COM_FOOTER_TITLES = {
    "contactez-nous",
    "politique de confidentialité",
    "politique sur les cookies",
    "conditions d'utilisation",
    "plus d'offres",
    "contact us",
    "cookie policy",
    "privacy policy",
    "terms of service",
    "condiciones de uso",
    "política de privacidad",
    "política de cookies",
    "contáctanos",
    "condizioni di servizio",
    "informativa sulla privacy",
    "informativa sui cookie",
    "contattaci!",
    "servicevoorwaarden",
    "privacybeleid",
    "cookiebeleid",
    "neem contact met ons op",
    "nutzungsbedingungen",
    "datenschutzerklärung",
    "cookie-richtlinie",
    "kontakt",
}

# Lien de redirection propre à une offre, imbriqué dans l'attribut href
# de la balise <a> du titre elle-même.
TALENT_COM_REDIRECT_RE = re.compile(
    r'href="(https://fr\.talent\.com/redirect\?id(?:=|&#x3D;)[a-f0-9]+[^"]{0,600})"'
)

# Lieu ("Ville, Région, Pays") puis entreprise, dans deux <td> de couleurs fixes
# juste après le lien du titre. Le <td> entreprise est parfois vide : Talent.com
# relaie aussi des annonces d'agences/agrégateurs qui ne communiquent pas l'employeur.
TALENT_COM_INFO_RE = re.compile(
    r'<td[^>]*style="[^"]*color:\s*#691f74[^"]*"[^>]*>\s*([^<]{1,150}?)\s*</td>\s*'
    r".*?"
    r'<td[^>]*style="[^"]*color:\s*#30183f[^"]*"[^>]*>\s*([^<]{0,150}?)\s*</td>',
    re.S,
)


def extract_talent_com(html: str, msg, patterns: dict) -> list[dict]:
    offers = []

    # Talent.com : titre en hyperlien (span ou a), suivi ville, entreprise
    title_iter = list(re.finditer(r"<a[^>]+talent\.com[^>]*>([^<]{5,100})</a>", html))

    for idx, title_m in enumerate(title_iter[:20]):
        titre = clean_entities(title_m.group(1)).strip()
        if len(titre) < 5 or "Afficher" in titre or "désabonner" in titre:
            continue
        if titre.rstrip(" ,.").lower() in TALENT_COM_FOOTER_TITLES:
            continue
        o = offer_base()
        o["titre"] = titre
        # Le lien de redirection propre à cette offre est imbriqué dans la
        # balise <a> du titre elle-même (son attribut href) ; un appariement
        # par index sur une liste à plat se désynchronise dès qu'une annonce
        # intercalée n'a pas de titre détecté par la regex ci-dessus.
        url_m = TALENT_COM_REDIRECT_RE.search(html, title_m.start())
        if url_m and url_m.start() < title_m.end():
            o["url"] = clean_entities(url_m.group(1))
            o["url_qualite"] = "email"

        info_m = TALENT_COM_INFO_RE.search(html[title_m.end() : title_m.end() + 2000])
        if info_m:
            lieu = clean_entities(info_m.group(1)).strip()
            o["ville"] = lieu.split(",")[0].strip()
            entreprise = clean_entities(info_m.group(2)).strip()
            if entreprise:
                o["entreprise"] = entreprise

        # Le type de contrat apparaît dans le titre lui-même (ex. "CDI – ...",
        # "MAINTENANCE TECHNIQUE H/F - CDD"), pas ailleurs dans l'e-mail —
        # une recherche globale mélangerait les contrats entre offres.
        contrat_m = re.search(r"\b(CDI|CDD|Alternance|Stage|Freelance|Indépendant)\b", titre, re.I)
        if contrat_m:
            o["type_contrat"] = contrat_m.group(1)
        offers.append(o)
    return offers
