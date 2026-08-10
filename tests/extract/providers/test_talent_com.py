from extract.providers.talent_com import extract_talent_com

HTML = """
<a href="https://fr.talent.com/redirect?id=abc123def456&extra=1">Développeur Ruby CDI</a>
<table>
<tr><td style="color: #691f74">Toulon, PACA, France</td></tr>
<tr><td style="color: #30183f">ACME Corp</td></tr>
</table>
"""

FOOTER_HTML = """
<a href="https://fr.talent.com/redirect?id=abc123def456">Contactez-nous</a>
"""


def test_extracts_offer_with_redirect_url_and_location(make_msg):
    offers = extract_talent_com(HTML, make_msg(), {})

    assert len(offers) == 1
    o = offers[0]
    assert o["titre"] == "Développeur Ruby CDI"
    assert o["url"] == "https://fr.talent.com/redirect?id=abc123def456&extra=1"
    assert o["url_qualite"] == "email"
    assert o["ville"] == "Toulon"
    assert o["entreprise"] == "ACME Corp"
    assert o["type_contrat"] == "CDI"


def test_skips_footer_links(make_msg):
    assert extract_talent_com(FOOTER_HTML, make_msg(), {}) == []


def test_returns_empty_list_when_no_talent_com_link(make_msg):
    assert extract_talent_com("<p>Rien</p>", make_msg(), {}) == []
