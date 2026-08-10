"""Text-cleaning utilities shared by the dedup key builder and the provider extractors."""

import re
import unicodedata


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
