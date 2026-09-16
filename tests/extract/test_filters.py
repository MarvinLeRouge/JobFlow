from extract.filters import (
    build_cle_dedup,
    extract_stack,
    is_blacklisted,
    is_hors_stack,
    is_stage_alternance,
)


def test_build_cle_dedup_normalizes_case_accents_and_separators():
    cle = build_cle_dedup(
        "Société Générale", "Aix-en-Provence", "Développeur PHP Senior (H/F)", "E000001"
    )
    assert cle == "societegenerale|aixenprovence|developpeurphp"


def test_build_cle_dedup_falls_back_to_row_id_when_fields_are_empty():
    assert build_cle_dedup("", "", "", "E000001") == "E000001|E000001|E000001"


def test_build_cle_dedup_is_stable_across_equivalent_variations():
    a = build_cle_dedup("ACME Corp", "Toulon", "Développeur Python H/F", "E000001")
    b = build_cle_dedup("acme-corp", "TOULON", "développeur python", "E000002")
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


def test_is_stage_alternance_matches_case_and_accent_insensitively():
    terms = ["alternance", "alternant", "stage", "stagiaire"]
    assert is_stage_alternance("Développeur en ALTERNANCE H/F", terms) == "alternance"


def test_is_stage_alternance_returns_none_when_no_term_matches():
    terms = ["alternance", "alternant", "stage", "stagiaire"]
    assert is_stage_alternance("Développeur Python CDI", terms) is None


def test_is_hors_stack_true_when_an_excluded_tag_is_present():
    excluded = ["C++", "C#", ".Net", "Java"]
    assert is_hors_stack("Java,Docker", excluded) is True


def test_is_hors_stack_false_when_only_javascript_is_present():
    excluded = ["C++", "C#", ".Net", "Java"]
    assert is_hors_stack("JS,React", excluded) is False


def test_is_hors_stack_false_when_stack_is_empty():
    excluded = ["C++", "C#", ".Net", "Java"]
    assert is_hors_stack("", excluded) is False


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
