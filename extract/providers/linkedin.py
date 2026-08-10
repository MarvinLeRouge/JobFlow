import re

from extract.providers import offer_base
from extract.text import clean_entities, clean_html


def extract_linkedin(html: str, msg, patterns: dict) -> list[dict]:
    offers = []
    # job IDs dans les ancres
    pairs = re.findall(r'jobs/view/(\d+)[^"]*"[^>]*>([^<]{5,100})</a>', html)
    seen = set()
    for job_id, titre in pairs:
        if job_id in seen:
            continue
        seen.add(job_id)
        titre = clean_entities(titre).strip()
        if len(titre) < 5:
            continue
        o = offer_base()
        o["titre"] = titre
        o["url"] = f"https://www.linkedin.com/jobs/view/{job_id}"
        o["url_qualite"] = "construite"

        # Entreprise et lieu : juste après le titre, dans un <p ...line-clamp-1...>
        # au format "Société · Lieu (mode de travail)" (ex. "Scalian · Ollioules (Sur site)").
        # Note : clean_html() aplatit les retours à la ligne, donc une recherche par
        # lignes ne fonctionne pas ici — on cible directement le <p> dans le HTML brut,
        # à une distance d'environ 4200 caractères du lien (au-delà de l'ancienne fenêtre de 800).
        idx = html.find(f"jobs/view/{job_id}")
        if idx >= 0:
            info_m = re.search(
                r'<p[^>]*class="[^"]*line-clamp-1[^"]*"[^>]*>\s*([^<]+? · [^<]+?)\s*</p>',
                html[idx : idx + 6000],
            )
            if info_m:
                info = clean_entities(info_m.group(1)).strip()
                company, _, lieu = info.partition(" · ")
                o["entreprise"] = company.strip()
                o["ville"] = re.sub(r"\s*\([^)]*\)\s*$", "", lieu).strip()

        contrat_m = re.search(
            r"\b(CDI|CDD|Alternance|Stage|Freelance)\b",
            clean_html(html[max(0, idx - 200) : idx + 500]) if idx >= 0 else "",
            re.I,
        )
        if contrat_m:
            o["type_contrat"] = contrat_m.group(1)

        offers.append(o)
    return offers
