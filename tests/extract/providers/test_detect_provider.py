from extract.providers import detect_provider

PATTERNS = {
    "_comment": {"sender_domains": ["ignored.example.com"]},
    "indeed_alerte": {"sender_domains": ["jobalert.indeed.com", "indeed.com"]},
    "indeed_match": {"sender_domains": ["match.indeed.com"]},
    "linkedin": {"sender_domains": ["linkedin.com"]},
}


def test_detect_provider_matches_a_registered_domain():
    key, config = detect_provider("linkedin.com", PATTERNS)

    assert key == "linkedin"
    assert config is PATTERNS["linkedin"]


def test_detect_provider_prefers_the_more_specific_domain_suffix():
    key, config = detect_provider("match.indeed.com", PATTERNS)

    assert key == "indeed_match"
    assert config is PATTERNS["indeed_match"]


def test_detect_provider_falls_back_to_the_less_specific_domain():
    key, config = detect_provider("jobalert.indeed.com", PATTERNS)

    assert key == "indeed_alerte"


def test_detect_provider_ignores_keys_starting_with_an_underscore():
    key, config = detect_provider("ignored.example.com", PATTERNS)

    assert (key, config) == (None, None)


def test_detect_provider_returns_none_none_when_nothing_matches():
    key, config = detect_provider("unknown.example.com", PATTERNS)

    assert (key, config) == (None, None)
