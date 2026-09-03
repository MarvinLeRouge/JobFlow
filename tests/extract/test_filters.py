from extract.filters import blacklist_category, build_cle_dedup, extract_stack, is_blacklisted


def test_build_cle_dedup_normalizes_case_accents_and_separators():
    cle = build_cle_dedup("Société Générale", "Aix-en-Provence", "Développeur PHP Senior (H/F)")
    assert cle == "societegenerale|aixenprovence|developpeurphp"


def test_build_cle_dedup_falls_back_to_placeholders_when_fields_are_empty():
    assert build_cle_dedup("", "", "") == "inconnu|inconnue|inconnu"


def test_build_cle_dedup_is_stable_across_equivalent_variations():
    a = build_cle_dedup("ACME Corp", "Toulon", "Développeur Python H/F")
    b = build_cle_dedup("acme-corp", "TOULON", "développeur python")
    assert a == b


def test_is_blacklisted_matches_case_and_accent_insensitively():
    blacklist = ["auxiliaire de vie", "nounou"]
    assert is_blacklisted("Auxiliaire De Vie H/F", blacklist) == "auxiliaire de vie"


def test_is_blacklisted_returns_none_when_no_term_matches():
    blacklist = ["auxiliaire de vie", "nounou"]
    assert is_blacklisted("Développeur Python", blacklist) is None


def test_is_blacklisted_returns_first_matching_blacklist_entry():
    blacklist = ["python", "developpeur"]
    assert is_blacklisted("Développeur Python", blacklist) == "python"


def test_extract_stack_finds_multiple_technologies():
    keywords = {"Python": ["python"], "React": ["react", "react.js"]}
    result = extract_stack("Recherche dev React.js avec exp Python", keywords)
    assert set(result.split(",")) == {"Python", "React"}


def test_extract_stack_respects_word_boundaries():
    keywords = {"PHP": ["php"]}
    result = extract_stack("Utilise phpstorm au quotidien", keywords)
    assert result == ""


def test_extract_stack_returns_empty_string_when_nothing_found():
    keywords = {"Java": ["java"]}
    assert extract_stack("Poste en vente pure", keywords) == ""


def test_blacklist_category_maps_term_to_its_configured_category():
    categories = {"commercial immobilier": "immobilier", "nounou": "aide à domicile"}
    assert blacklist_category("commercial immobilier", categories) == "immobilier"


def test_blacklist_category_falls_back_to_the_term_itself_when_unmapped():
    categories = {"commercial immobilier": "immobilier"}
    assert blacklist_category("babysitter", categories) == "babysitter"
