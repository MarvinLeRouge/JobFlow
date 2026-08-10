"""Résolution du département depuis un nom de ville : table locale, puis fallback Nominatim."""

import time

from extract.text import strip_accents

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
