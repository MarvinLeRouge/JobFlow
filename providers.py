"""Shared sender-domain routing: maps an email's sender domain to its
provider folder under sources/, using config/scraping_patterns.json."""

import json
import re
from pathlib import Path


def load_domain_map(patterns_file: Path) -> dict:
    """Build {sender_domain: expected_folder} from scraping_patterns.json."""
    if not patterns_file.exists():
        return {}
    with patterns_file.open(encoding="utf-8") as f:
        patterns = json.load(f)
    mapping = {}
    for key, p in patterns.items():
        if key.startswith("_"):
            continue
        folder = p.get("folder")
        for domain in p.get("sender_domains", []):
            if domain and folder:
                mapping[domain.lower()] = folder
    return mapping


def sender_domain(from_header: str) -> str:
    """Extract the domain from a From: header, e.g. 'Foo <bar@baz.com>' -> 'baz.com'."""
    match = re.search(r"@([\w.\-]+)", from_header or "")
    return match.group(1).lower() if match else ""


def expected_folder(domain: str, domain_map: dict) -> str | None:
    """Find the expected folder for this domain, testing the full domain
    then parent suffixes (e.g. 'jobalert.indeed.com' -> 'indeed.com' -> 'com')."""
    parts = domain.split(".")
    for i in range(len(parts)):
        candidate = ".".join(parts[i:])
        if candidate in domain_map:
            return domain_map[candidate]
    return None
