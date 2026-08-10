from extract.providers.jobijoba import extract_jobijoba

HTML = """
<a href="https://emails.jobijoba.com/clic/abcde1234-1234-5678-90ab-cdefabcdefab/1/deadbeef/xyz">
<strong title="Développeur Java - hellowork.com">Développeur Java</strong>
<span>Toulon</span>
<span style="color:#000000">ACME Corp</span>
CDI
</a>
"""


def test_extracts_offer_and_source_platform_from_title_attribute(make_msg):
    offers = extract_jobijoba(HTML, make_msg(), {})

    assert len(offers) == 1
    o = offers[0]
    assert o["titre"] == "Développeur Java"
    assert o["entreprise"] == "ACME Corp"
    assert o["ville"] == "Toulon"
    assert o["type_contrat"] == "CDI"
    assert o["url"].startswith("https://emails.jobijoba.com/clic/")
    assert o["url_qualite"] == "email"
    assert o["notes"] == "Via Jobijoba (hellowork.com)"


def test_returns_empty_list_when_no_title_attribute_matches(make_msg):
    assert extract_jobijoba("<p>Rien</p>", make_msg(), {}) == []
