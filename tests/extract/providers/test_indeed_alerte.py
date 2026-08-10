from extract.providers.indeed_alerte import extract_indeed_alerte

HTML = """
<h2><a href="https://fr.indeed.com/rc/clk?jk=abcdef0123456789&from=alert">
Développeur Backend</a></h2>
<table>
<tr><td style="color:#2d2d2d;font-size:14px;line-height:21px">ACME Corp</td></tr>
<tr><td style="color:#2d2d2d;font-size:14px;line-height:21px">Toulon (83)</td></tr>
</table>
CDI
"""


def test_extracts_offer_via_jk_and_normalizes_url(make_msg):
    offers = extract_indeed_alerte(HTML, make_msg(), {})

    assert len(offers) == 1
    o = offers[0]
    assert o["titre"] == "Développeur Backend"
    assert o["url"] == "https://fr.indeed.com/viewjob?jk=abcdef0123456789"
    assert o["url_qualite"] == "construite"
    assert o["entreprise"] == "ACME Corp"
    assert o["ville"] == "Toulon"
    assert o["dept"] == "83"
    assert o["type_contrat"] == "CDI"


def test_returns_empty_list_when_no_h2_block_matches(make_msg):
    assert extract_indeed_alerte("<p>Rien</p>", make_msg(), {}) == []


def test_deduplicates_on_jk_across_blocks(make_msg):
    offers = extract_indeed_alerte(HTML + HTML, make_msg(), {})
    assert len(offers) == 1
