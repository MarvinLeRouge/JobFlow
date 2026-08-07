import json
from pathlib import Path

import pytest

from providers import expected_folder, load_domain_map, sender_domain


@pytest.fixture
def patterns_file(tmp_path: Path) -> Path:
    data = {
        "_comment": "ignored",
        "indeed_alerte": {
            "folder": "indeed",
            "sender_domains": ["jobalert.indeed.com", "indeed.com"],
        },
        "linkedin": {
            "folder": "linkedin",
            "sender_domains": ["linkedin.com"],
        },
    }
    path = tmp_path / "scraping_patterns.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_domain_map_builds_domain_to_folder_mapping(patterns_file):
    mapping = load_domain_map(patterns_file)
    assert mapping == {
        "jobalert.indeed.com": "indeed",
        "indeed.com": "indeed",
        "linkedin.com": "linkedin",
    }


def test_load_domain_map_missing_file_returns_empty_dict(tmp_path):
    assert load_domain_map(tmp_path / "does_not_exist.json") == {}


def test_sender_domain_extracts_domain_from_from_header():
    assert sender_domain("Foo Bar <foo@jobalert.indeed.com>") == "jobalert.indeed.com"


def test_sender_domain_returns_empty_string_when_no_match():
    assert sender_domain("not an email") == ""


def test_expected_folder_matches_exact_domain(patterns_file):
    mapping = load_domain_map(patterns_file)
    assert expected_folder("jobalert.indeed.com", mapping) == "indeed"


def test_expected_folder_falls_back_to_parent_suffix(patterns_file):
    mapping = load_domain_map(patterns_file)
    assert expected_folder("sub.linkedin.com", mapping) == "linkedin"


def test_expected_folder_unknown_domain_returns_none(patterns_file):
    mapping = load_domain_map(patterns_file)
    assert expected_folder("unknown.example.com", mapping) is None
