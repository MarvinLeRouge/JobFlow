from extract.providers.indeed_match import extract_indeed_match

HTML = """
<p>Bonjour Jean, une offre vous correspond.</p>
<a href="https://cts.indeed.com/v3/RANDOMTOKEN123">Voir l'offre</a>
<p>ACME Corp La Valette-du-Var (83) Salaire: 40 000€ CDI</p>
"""


def test_extracts_title_and_company_from_subject(make_msg):
    msg = make_msg(subject="Développeur Full Stack – ACME Corp")
    offers = extract_indeed_match(HTML, msg, {})

    assert len(offers) == 1
    o = offers[0]
    assert o["titre"] == "Développeur Full Stack"
    assert o["entreprise"] == "ACME Corp"
    assert o["url"] == "https://cts.indeed.com/v3/RANDOMTOKEN123"
    assert o["url_qualite"] == "email"
    assert o["ville"] == "La Valette-du-Var"
    assert o["dept"] == "83"
    assert o["type_contrat"] == "CDI"


def test_returns_empty_list_when_subject_has_no_dash_separator(make_msg):
    msg = make_msg(subject="Alerte emploi hebdomadaire")
    assert extract_indeed_match(HTML, msg, {}) == []
