from extract.providers.france_travail import extract_france_travail

HTML = """
<a href="https://candidat.francetravail.fr/offres/recherche/detail/208HNZK?type=article">
<span>Développeur Python<br><span>ACME Corp</span><span>83 - Toulon</span></span></a>
<table><tr><td>CDI</td></tr></table>
"""


def test_extracts_title_company_location_and_contract(make_msg):
    offers = extract_france_travail(HTML, make_msg(), {})

    assert len(offers) == 1
    o = offers[0]
    assert o["titre"] == "Développeur Python"
    assert o["entreprise"] == "ACME Corp"
    assert o["ville"] == "Toulon"
    assert o["dept"] == "83"
    assert o["type_contrat"] == "CDI"
    assert o["url"] == "https://candidat.francetravail.fr/offres/recherche/detail/208HNZK"
    assert o["url_qualite"] == "construite"
    assert o["notes"] == "Offre n°208HNZK"


def test_returns_empty_list_when_no_offer_block_matches(make_msg):
    assert extract_france_travail("<p>Aucune offre ici</p>", make_msg(), {}) == []


def test_deduplicates_repeated_offer_ids_within_the_same_email(make_msg):
    offers = extract_france_travail(HTML + HTML, make_msg(), {})
    assert len(offers) == 1
