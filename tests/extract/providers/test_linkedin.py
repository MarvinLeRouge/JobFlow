from extract.providers.linkedin import extract_linkedin

HTML = """
<a href="https://www.linkedin.com/jobs/view/1234567890/?trk=abc">Ingénieur Logiciel</a>
<p class="line-clamp-1">Scalian · Toulon (Sur site)</p>
CDI
"""


def test_extracts_offer_from_job_view_link(make_msg):
    offers = extract_linkedin(HTML, make_msg(), {})

    assert len(offers) == 1
    o = offers[0]
    assert o["titre"] == "Ingénieur Logiciel"
    assert o["url"] == "https://www.linkedin.com/jobs/view/1234567890"
    assert o["url_qualite"] == "construite"
    assert o["entreprise"] == "Scalian"
    assert o["ville"] == "Toulon"
    assert o["type_contrat"] == "CDI"


def test_returns_empty_list_when_no_job_view_link(make_msg):
    assert extract_linkedin("<p>Rien</p>", make_msg(), {}) == []


def test_deduplicates_on_job_id(make_msg):
    offers = extract_linkedin(HTML + HTML, make_msg(), {})
    assert len(offers) == 1
