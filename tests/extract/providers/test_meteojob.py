from extract.providers.meteojob import extract_meteojob_company

HTML = """
<a class="hotoffer-cta-link" href="https://www.meteojob.com/jobs/123456?utm=abc">Voir l'offre</a>
<p>Toulon (83) - CDI</p>
"""


def test_extracts_title_and_company_from_subject(make_msg):
    msg = make_msg(subject="ACME Corp recrute un Développeur PHP")
    offers = extract_meteojob_company(HTML, msg, {})

    assert len(offers) == 1
    o = offers[0]
    assert o["titre"] == "Développeur PHP"
    assert o["entreprise"] == "ACME Corp"
    assert o["url"] == "https://www.meteojob.com/jobs/123456?utm=abc"
    assert o["url_qualite"] == "construite"
    assert o["ville"] == "Toulon"
    assert o["dept"] == "83"
    assert o["type_contrat"] == "CDI"


def test_returns_empty_list_when_subject_does_not_match_pattern(make_msg):
    msg = make_msg(subject="Newsletter Meteojob de la semaine")
    assert extract_meteojob_company("<p>Rien</p>", msg, {}) == []
