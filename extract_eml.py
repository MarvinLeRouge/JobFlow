#!/usr/bin/env python3
"""
extract_eml.py — Scraper principal : extrait les offres depuis les EML sources.

Usage : python3 extract_eml.py [--dry-run]

- Lit logs/email_ledger.json → fichiers à traiter (statut_extraction = PENDING)
- Détecte le provider     → config/scraping_patterns.json
- Extrait les offres      → output/import_YYYYMMDD.csv  (fichier daté par run)
- Dédup sur Cle_dedup     → Doublon_ID si doublon cross-provider
- Géocode les villes      → config/config.json + Nominatim (fallback)
- Journalise              → logs/YYYYMMDD-HHMM_extraction.log
                            logs/extraction_history.csv

Chaque run produit un fichier import_YYYYMMDD.csv contenant uniquement
les nouvelles offres de ce run. À importer dans Google Sheets via
Données → Importer → Ajouter aux données actuelles.
"""

import argparse
import csv
import email
import json
import re
import time
import unicodedata
from datetime import datetime
from email import policy
from pathlib import Path
from zoneinfo import ZoneInfo

from ledger import load_ledger, save_ledger
from providers import sender_domain

# ── Chemins ───────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent
CONFIG_DIR = ROOT / "config"
LOGS_DIR = ROOT / "logs"
OUTPUT_DIR = ROOT / "output"
SOURCES_DIR = ROOT / "sources"

CONFIG_FILE = CONFIG_DIR / "config.json"
PATTERNS_FILE = CONFIG_DIR / "scraping_patterns.json"
LEDGER_FILE = LOGS_DIR / "email_ledger.json"
OFFRES_CSV = OUTPUT_DIR / "offres.csv"  # archive locale cumulative (référence dédup)
HISTORY_CSV = LOGS_DIR / "extraction_history.csv"
# IMPORT_CSV est défini dans main() : output/import_YYYYMMDD.csv
IMPORT_CSV = None

LOCAL_TZ = ZoneInfo("Europe/Paris")

# ── Chargement config ─────────────────────────────────────────────────────────


def load_config():
    with CONFIG_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def load_patterns():
    with PATTERNS_FILE.open(encoding="utf-8") as f:
        return json.load(f)


# ── Utilitaires texte ─────────────────────────────────────────────────────────


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def normalize(s: str) -> str:
    """Minuscule, sans accents, sans espaces/tirets → pour Cle_dedup."""
    return re.sub(r"[\s\-_/]+", "", strip_accents(s.lower()))


def clean_entities(s: str) -> str:
    for ent, ch in [
        ("&amp;", "&"),
        ("&nbsp;", " "),
        ("&#x27;", "'"),
        ("&#39;", "'"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
        ("&hellip;", "…"),
        ("&middot;", "·"),
        ("&emsp;", " "),
        ("&#8202;", ""),
        ("&#8203;", ""),
        ("&#8199;", ""),
        ("&#847;", ""),
        ("&shy;", ""),
        ("&#x3D;", "="),
    ]:
        s = s.replace(ent, ch)
    return s


def clean_html(html: str) -> str:
    """HTML → texte brut lisible."""
    t = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
    t = re.sub(r"<script[^>]*>.*?</script>", "", t, flags=re.DOTALL)
    t = re.sub(r"<[^>]+>", " ", t)
    t = clean_entities(t)
    return re.sub(r"\s+", " ", t).strip()


TITRE_STOPWORDS = frozenset(
    {
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "du",
        "de",
        "d",
        "l",
        "en",
        "et",
        "ou",
        "sur",
        "pour",
        "par",
        "avec",
        "sans",
        "au",
        "aux",
        "ce",
        "cet",
        "cette",
        "ces",
        "senior",
        "junior",
        "jr",
        "sr",
    }
)


def titre_slug(titre: str) -> str:
    """Slug de titre pour la clé de dédup : sans mots vides ni mentions H/F, tronqué à 25 chars."""
    t = re.sub(r"\bH/F\b|\bF/H\b|\bH/F/X\b|\bM/F\b", "", titre, flags=re.IGNORECASE)
    t = re.sub(r"\(.*?\)|\[.*?\]", "", t)
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", t)
    parts = [normalize(w) for w in words if normalize(w) not in TITRE_STOPWORDS]
    return "".join(parts)[:25]


def build_cle_dedup(entreprise: str, ville: str, titre: str) -> str:
    e = normalize(entreprise) or "inconnu"
    v = normalize(ville) or "inconnue"
    t = titre_slug(titre) or "inconnu"
    return f"{e}|{v}|{t}"


# ── Blacklist titres ──────────────────────────────────────────────────────────


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


# ── Stack keywords ────────────────────────────────────────────────────────────


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


# ── Géolocalisation ───────────────────────────────────────────────────────────

_nominatim_cache: dict = {}
_last_nominatim_call: float = 0.0


def get_dept(ville: str, ville_dept_map: dict) -> str:
    """Retourne le numéro de département depuis la ville."""
    if not ville:
        return ""
    key = strip_accents(ville.lower().strip())
    if key in ville_dept_map:
        return ville_dept_map[key]
    # Tentative partielle : juste le premier mot
    first_word = key.split()[0] if key.split() else ""
    for k, v in ville_dept_map.items():
        if k.startswith(first_word) and first_word:
            return v
    # Fallback Nominatim
    return _nominatim_dept(ville)


def _nominatim_dept(ville: str) -> str:
    global _last_nominatim_call
    if ville in _nominatim_cache:
        return _nominatim_cache[ville]
    try:
        import requests

        elapsed = time.time() - _last_nominatim_call
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": f"{ville}, France", "format": "json", "limit": 1, "addressdetails": 1},
            headers={"User-Agent": "job-search-tracker/1.0"},
            timeout=5,
        )
        _last_nominatim_call = time.time()
        data = r.json()
        if data:
            postcode = data[0].get("address", {}).get("postcode", "")
            dept = postcode[:2] if postcode else ""
            _nominatim_cache[ville] = dept
            return dept
    except Exception:
        pass
    _nominatim_cache[ville] = ""
    return ""


# ── Parsing EML ───────────────────────────────────────────────────────────────


def get_eml_parts(eml_path: Path):
    """Retourne (msg, html_body, text_body)."""
    with eml_path.open("rb") as f:
        msg = email.message_from_bytes(f.read(), policy=policy.default)
    html, text = "", ""
    for part in msg.walk():
        ct = part.get_content_type()
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        decoded = payload.decode(charset, errors="replace")
        if ct == "text/html" and not html:
            html = decoded
        elif ct == "text/plain" and not text:
            text = decoded
    return msg, html, text


def detect_provider(domain: str, patterns: dict) -> tuple[str, dict] | tuple[None, None]:
    """Retourne (provider_key, provider_config) ou (None, None).

    Plusieurs providers peuvent déclarer un domaine suffixe commun
    (ex: indeed_alerte → indeed.com, indeed_match → match.indeed.com) ;
    on retient le domaine le plus spécifique (le plus de composants)."""
    parts = domain.split(".")
    best = None
    best_specificity = 0
    for key, p in patterns.items():
        if key.startswith("_"):
            continue
        for d in p.get("sender_domains", []):
            d_parts = d.lower().split(".")
            if parts[-len(d_parts) :] == d_parts and len(d_parts) > best_specificity:
                best = (key, p)
                best_specificity = len(d_parts)
    return best if best else (None, None)


# ── Extracteurs par provider ──────────────────────────────────────────────────


def _offer_base() -> dict:
    return {
        "titre": "",
        "entreprise": "",
        "ville": "",
        "dept": "",
        "type_contrat": "",
        "salaire_min": "",
        "salaire_max": "",
        "url": "",
        "url_qualite": "vide",
        "notes": "",
    }


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

        o = _offer_base()
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

        o = _offer_base()
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


def extract_indeed_match(html: str, msg, patterns: dict) -> list[dict]:
    subject = msg.get("Subject", "")
    # Subject : "TITRE – COMPANY" — seul le tiret cadratin (–, U+2013) sépare titre et
    # entreprise ; les tirets simples (-) et cadratins longs (—) peuvent apparaître dans
    # le titre lui-même (ex. "PHP - REACT (H/F) – Société"), d'où le split sur la
    # DERNIÈRE occurrence de " – ".
    text = clean_html(html)

    o = _offer_base()
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
        o = _offer_base()
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


def extract_meteojob_company(html: str, msg, patterns: dict) -> list[dict]:
    subject = msg.get("Subject", "").strip()
    # Subject : "  COMPANY recrute un TITRE  "
    subj_m = re.match(r"^\s*(.+?)\s+recrute un\s+(.+?)\s*$", subject, re.I)

    o = _offer_base()
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

        o = _offer_base()
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
        o = _offer_base()
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


# Dispatch table
EXTRACTORS = {
    "france_travail": extract_france_travail,
    "indeed_alerte": extract_indeed_alerte,
    "indeed_match": extract_indeed_match,
    "linkedin": extract_linkedin,
    "meteojob_company": extract_meteojob_company,
    "meteojob_digest": None,  # skip
    "jobijoba_alerte": extract_jobijoba,
    "jobijoba_digest": None,  # skip
    "talent_com": extract_talent_com,
    "hellowork": None,  # patterns à définir
}

# ── Gestion CSV ───────────────────────────────────────────────────────────────


def load_dedup_map() -> tuple[dict, int]:
    """Retourne ({cle_dedup: id}, max_e_number) depuis offres.csv."""
    dedup = {}
    max_e = 0
    if not OFFRES_CSV.exists():
        return dedup, max_e
    with OFFRES_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            cle = row.get("Cle_dedup", "")
            rid = row.get("ID", "")
            if cle:
                dedup[cle] = rid
            if rid.startswith("E"):
                try:
                    max_e = max(max_e, int(rid[1:]))
                except ValueError:
                    pass
    return dedup, max_e


def has_prior_imports() -> bool:
    """Retourne True si au moins un fichier import_*.csv existe déjà dans output/."""
    return any(OUTPUT_DIR.glob("import_*.csv"))


def ensure_offres_csv(headers: list, write_import_headers: bool):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not OFFRES_CSV.exists():
        with OFFRES_CSV.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f, delimiter=";").writerow(headers)
    # Créer le fichier d'import du run
    if IMPORT_CSV and not IMPORT_CSV.exists():
        with IMPORT_CSV.open("w", newline="", encoding="utf-8") as f:
            if write_import_headers:
                csv.writer(f, delimiter=";").writerow(headers)
            # sinon fichier vide — les données seront appendées sans en-tête


def append_offres(rows: list[dict], headers: list):
    # Archive locale cumulative (pour la déduplication)
    with OFFRES_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
        writer.writerows(rows)
    # Fichier d'import daté (nouvelles lignes du run → à importer dans Sheets)
    if IMPORT_CSV:
        with IMPORT_CSV.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, delimiter=";", extrasaction="ignore")
            writer.writerows(rows)


# ── Logging ───────────────────────────────────────────────────────────────────


def write_run_log(run_dt: datetime, entries: list[str], stats: dict, log_path: Path):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        f.write(f"=== Extraction EML — {run_dt.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n")
        for line in entries:
            f.write(line + "\n")
        f.write("\n--- RÉSUMÉ ---\n")
        for k, v in stats.items():
            f.write(f"  {k}: {v}\n")


def append_history(run_dt: datetime, stats: dict):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "Date_run",
        "Fichiers_traites",
        "Offres_extraites",
        "Doublons",
        "Ignores",
        "Erreurs",
        "Dry_run",
    ]
    exists = HISTORY_CSV.exists()
    with HISTORY_CSV.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "Date_run": run_dt.strftime("%Y-%m-%dT%H:%M:%S"),
                "Fichiers_traites": stats.get("fichiers_ok", 0),
                "Offres_extraites": stats.get("offres_ecrites", 0),
                "Doublons": stats.get("doublons", 0),
                "Ignores": stats.get("ignores", 0),
                "Erreurs": stats.get("erreurs", 0),
                "Dry_run": stats.get("dry_run", False),
            }
        )


# ── Main ──────────────────────────────────────────────────────────────────────


def main(dry_run: bool, force_headers: bool | None = None):
    """
    force_headers :
      None  → automatique : headers si aucun import_*.csv existant, sinon sans
      True  → forcer headers (--with-headers)
      False → forcer sans headers (--no-headers)
    """
    global IMPORT_CSV
    run_dt = datetime.now(LOCAL_TZ)
    log_path = LOGS_DIR / f"{run_dt.strftime('%Y%m%d-%H%M')}_extraction.log"
    log_entries: list[str] = []

    if not dry_run:
        IMPORT_CSV = OUTPUT_DIR / f"import_{run_dt.strftime('%Y%m%d')}.csv"

    if force_headers is None:
        write_import_headers = not has_prior_imports()
        headers_reason = (
            "auto (aucun import existant)"
            if write_import_headers
            else "auto (imports existants détectés)"
        )
    else:
        write_import_headers = force_headers
        headers_reason = "forcé via --with-headers" if force_headers else "forcé via --no-headers"

    def log(msg: str, level: str = "INFO"):
        prefix = {"INFO": "  ", "WARN": "⚠ ", "ERR ": "✗ ", "IGN ": "— "}
        log_entries.append(f"[{level}] {msg}")
        print(prefix.get(level, "  ") + msg)

    config = load_config()
    patterns = load_patterns()
    headers = config["offres_csv_headers"]
    keywords = config["stack_keywords"]
    blacklist = config.get("blacklist_titres", [])
    ville_dept = {k.lower(): v for k, v in config["ville_dept"].items()}

    ledger = load_ledger(LEDGER_FILE)
    pending = sorted(
        (
            mid
            for mid, entry in ledger.items()
            if entry.get("statut_extraction", "PENDING") == "PENDING"
        ),
        key=lambda mid: ledger[mid].get("date_email", ""),
    )

    if not pending:
        print("Aucun fichier EML en attente de traitement.")
        return

    dedup_map, max_e_id = load_dedup_map()
    ensure_offres_csv(headers, write_import_headers)

    stats = {
        "fichiers_ok": 0,
        "fichiers_partiel": 0,
        "erreurs": 0,
        "ignores": 0,
        "offres_ecrites": 0,
        "doublons": 0,
        "blacklistes": 0,
        "dry_run": dry_run,
    }

    total = len(pending)
    headers_label = f"{'avec' if write_import_headers else 'sans'} en-tête ({headers_reason})"
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Traitement de {total} fichier(s) EML")
    if not dry_run and IMPORT_CSV:
        print(f"  → {IMPORT_CSV.name}  [{headers_label}]")
    print()

    for idx, message_id in enumerate(pending, 1):
        entry = ledger[message_id]
        rel_path = entry.get("fichier", "")
        eml_path = SOURCES_DIR / rel_path
        date_email = entry.get("date_email", "")[:10]

        pct = idx / total * 100
        print(f"[{idx}/{total} — {pct:.0f}%] {rel_path}")

        if not eml_path.exists():
            log(f"Fichier introuvable : {eml_path}", "ERR ")
            entry["statut_extraction"] = "ERREUR"
            stats["erreurs"] += 1
            continue

        try:
            msg, html, _text = get_eml_parts(eml_path)
        except Exception as e:
            log(f"Impossible de lire {rel_path} : {e}", "ERR ")
            entry["statut_extraction"] = "ERREUR"
            stats["erreurs"] += 1
            continue

        domain = sender_domain(msg.get("From", ""))
        provider_key, provider_cfg = detect_provider(domain, patterns)

        if provider_key is None:
            log(f"Provider inconnu (domaine: {domain}) — {rel_path}", "WARN")
            entry["statut_extraction"] = "ERREUR"
            stats["erreurs"] += 1
            continue

        if provider_cfg.get("skip"):
            log(f"EML ignoré [{provider_key}] : {rel_path}", "IGN ")
            entry["statut_extraction"] = "IGNORE"
            stats["ignores"] += 1
            continue

        extractor = EXTRACTORS.get(provider_key)
        if extractor is None:
            log(f"EML ignoré [pas d'extracteur pour {provider_key}] : {rel_path}", "IGN ")
            entry["statut_extraction"] = "IGNORE"
            stats["ignores"] += 1
            continue

        try:
            raw_offers = extractor(html, msg, provider_cfg)
        except Exception as e:
            log(f"Erreur d'extraction [{provider_key}] {rel_path} : {e}", "ERR ")
            entry["statut_extraction"] = "ERREUR"
            stats["erreurs"] += 1
            continue

        if not raw_offers:
            log(f"Aucune offre extraite [{provider_key}] : {rel_path}", "WARN")
            log(f"  → Sujet : {msg.get('Subject', '?')[:80]}", "WARN")
            entry["statut_extraction"] = "PARTIEL"
            stats["fichiers_partiel"] += 1
            continue

        source_display = {
            "france_travail": "France Travail",
            "indeed_alerte": "Indeed",
            "indeed_match": "Indeed",
            "linkedin": "LinkedIn",
            "meteojob_company": "Meteojob",
            "jobijoba_alerte": "Jobijoba",
            "talent_com": "Talent.com",
        }.get(provider_key, provider_key)

        new_rows = []
        offer_errors = 0

        for offer in raw_offers:
            if not offer.get("titre"):
                offer_errors += 1
                log(f"  Offre ignorée (titre vide) dans {rel_path}", "WARN")
                continue

            max_e_id += 1
            eid = f"E{max_e_id:06d}"

            if not offer.get("dept") and offer.get("ville"):
                offer["dept"] = get_dept(offer["ville"], ville_dept)

            search_text = offer["titre"] + " " + offer.get("notes", "")
            stack = extract_stack(search_text, keywords)

            cle = build_cle_dedup(
                offer.get("entreprise", ""),
                offer.get("ville", ""),
                offer["titre"],
            )

            doublon_id = ""
            if cle in dedup_map:
                doublon_id = dedup_map[cle]
                stats["doublons"] += 1
                log(f"  Doublon : {cle} → {doublon_id}", "INFO")
            else:
                dedup_map[cle] = eid

            notes = offer.get("notes", "")

            bl_term = is_blacklisted(offer["titre"], blacklist)
            if bl_term:
                stats["blacklistes"] += 1
                marker = f"⛔ Blacklisté: {bl_term}"
                notes = f"{notes} | {marker}" if notes else marker

            row = {
                "ID": eid,
                "Traite": "FALSE",
                "Date_decouverte": date_email,
                "Source": source_display,
                "Titre": offer["titre"],
                "Entreprise": offer.get("entreprise", ""),
                "Cle_dedup": cle,
                "Doublon_ID": doublon_id,
                "Ville": offer.get("ville", ""),
                "Dept": offer.get("dept", ""),
                "Type_contrat": offer.get("type_contrat", ""),
                "Salaire_min": offer.get("salaire_min", ""),
                "Salaire_max": offer.get("salaire_max", ""),
                "URL": offer.get("url", ""),
                "URL_qualite": offer.get("url_qualite", "vide"),
                "URL_redirect": "",
                "Stack": stack,
                "Raison_exclusion": f"Blacklisté: {bl_term}" if bl_term else "",
                "Date_candidature": "",
                "Notes": notes,
                "Message_ID": message_id,
            }
            new_rows.append(row)

        if new_rows and not dry_run:
            append_offres(new_rows, headers)

        nb_ok = len(new_rows)
        nb_err = offer_errors
        stats["offres_ecrites"] += nb_ok

        statut = "OK" if nb_err == 0 else "PARTIEL"
        entry["statut_extraction"] = statut

        if statut == "OK":
            stats["fichiers_ok"] += 1
            log(f"  {nb_ok} offre(s) {'simulées' if dry_run else 'écrites'}", "INFO")
        else:
            stats["fichiers_partiel"] += 1
            log(f"  {nb_ok} offre(s) OK, {nb_err} ignorée(s)", "WARN")

    if not dry_run:
        save_ledger(LEDGER_FILE, ledger)

    print(f"\n{'='*55}")
    print(f"{'[DRY-RUN] ' if dry_run else ''}RAPPORT DE RUN — {run_dt.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}")
    print(f"  Fichiers traités  : {stats['fichiers_ok'] + stats['fichiers_partiel']}/{total}")
    print(f"  Offres écrites    : {stats['offres_ecrites']}")
    print(f"  Doublons détectés : {stats['doublons']}")
    print(f"  Blacklistés       : {stats['blacklistes']}")
    print(f"  Fichiers ignorés  : {stats['ignores']}")
    print(f"  Fichiers partiels : {stats['fichiers_partiel']}")
    print(f"  Erreurs           : {stats['erreurs']}")
    if stats["erreurs"] or stats["fichiers_partiel"]:
        print(f"\n  ⚠  Détails dans : {log_path.name}")
    if not dry_run and IMPORT_CSV and stats["offres_ecrites"] > 0:
        print(f"\n  → À importer dans Google Sheets : {IMPORT_CSV.name}")
        print("     Données → Importer → Ajouter aux données actuelles")
    print(f"{'='*55}\n")

    if not dry_run:
        write_run_log(run_dt, log_entries, stats, log_path)
        append_history(run_dt, stats)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Simule l'extraction sans écrire de fichiers"
    )
    hdr = parser.add_mutually_exclusive_group()
    hdr.add_argument(
        "--with-headers",
        action="store_true",
        help="Forcer la présence de l'en-tête dans le fichier import",
    )
    hdr.add_argument(
        "--no-headers",
        action="store_true",
        help="Forcer l'absence de l'en-tête dans le fichier import",
    )
    args = parser.parse_args()

    force_headers = None
    if args.with_headers:
        force_headers = True
    elif args.no_headers:
        force_headers = False

    main(dry_run=args.dry_run, force_headers=force_headers)
