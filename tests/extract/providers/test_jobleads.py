from extract.providers.jobleads import extract_jobleads

# Gabarit "offre unique du jour" : le <a href> englobe tout le bloc (titre,
# entreprise, lieu/mode, contrat/salaire), chaque ligne secondaire est préfixée
# par &bull; dans le même <div> que son texte.
JOB_URL = "https://www.jobleads.com/fr/job/consultant-devops--ollioules--ed8c0008a84b8a214a020ccddb1d474f7"
HTML_SINGLE_OFFER = f"""
<a href="{JOB_URL}?kuuid=abc&utm_source=rr_settings" target="_blank">
  <div style="color: #100F0E; font-size: 20px; font-weight: 700;">
    Consultant DevOps
  </div>
  <div style="color: #484745; font-size: 16px;">
    &bull; Les-Filles-Et-Les-Gar
  </div>
  <div style="color: #484745; font-size: 16px;">
    &bull; Ollioules | Sur place
  </div>
  <div style="color: #484745; font-size: 16px;">
    &bull; Plein temps | EUR 65 000 - 90 000
  </div>
  <td style="color: #A03E3C;">Voir tous les détails et postuler</td>
</a>
"""

# Gabarit "alerte multi-offres" : le lien CTA vient après le contenu de chaque
# carte, la puce "•" occupe son propre <div> séparé de celui du texte, et
# l'ordre contrat/salaire est inversé par rapport au gabarit "offre unique".
HTML_DIGEST_CARD = """
<!-- Top section: Title, Company, Location/Chips -->
<div style="color: #100F0E; font-size: 20px; font-weight: 600;">
  {titre}
</div>
<div style="color: #272625; font-size: 16px;">
  {entreprise}
</div>
<div style="color: #484745; font-size: 16px;">•</div>
<div style="color: #484745; font-size: 16px;">
  {lieu} | {mode}
</div>
<div style="color: #484745; font-size: 16px;">•</div>
<div style="color: #484745; font-size: 16px;">
  EUR {sal_min} 000 - {sal_max} 000 | {contrat}
</div>
<a href="https://www.jobleads.com/job/{job_id}?kuuid=abc&utm_source=x" style="color: #B43332;">
  Afficher l’offre d’emploi
</a>
"""

HTML_DIGEST = HTML_DIGEST_CARD.format(
    titre="Développeur Back-End PHP H/F (F/H)",
    entreprise="Synanto",
    lieu="Marseille",
    mode="Sur place",
    sal_min=55,
    sal_max=75,
    contrat="Plein temps",
    job_id="e4d8fe5c8274fd4f47421fd46f59fe716",
) + HTML_DIGEST_CARD.format(
    titre="Développeur·euse Front-end Senior",
    entreprise="Smart Tribune",
    lieu="Marseille",
    mode="Hybride",
    sal_min=70,
    sal_max=100,
    contrat="Plein temps",
    job_id="eb84384e47313314bfaa04b016eff2cb1",
)

# Régression : la "Benefits Highlight Row" (présente pour certains
# destinataires, cf. commentaire HTML réel "A/B test treatment only") pousse
# le lien CTA de la DERNIÈRE carte très loin après son titre - rien ne la
# borne par un titre suivant, contrairement aux cartes précédentes.
LAST_CARD_JOB_URL = (
    "https://www.jobleads.com/fr/job/cloud-automation-platform-engineer-aws-devsecops"
    "-h-f--la-ciotat--e7b522d99d10b4b8aa7ee8f5df07b9485"
)
HTML_DIGEST_LAST_CARD_WITH_BENEFITS_ROW = (
    HTML_DIGEST_CARD.format(
        titre="Développeur Back-End PHP H/F (F/H)",
        entreprise="Synanto",
        lieu="Marseille",
        mode="Sur place",
        sal_min=55,
        sal_max=75,
        contrat="Plein temps",
        job_id="e4d8fe5c8274fd4f47421fd46f59fe716",
    )
    + """
<!-- Top section: Title, Company, Location/Chips -->
<div style="color: #100F0E; font-size: 20px; font-weight: 600;">
  Cloud Automation & Platform Engineer (AWS / DevSecOps) (H/F)
</div>
<div style="color: #272625; font-size: 16px;">
  DIGWAY
</div>
<div style="color: #484745; font-size: 16px;">•</div>
<div style="color: #484745; font-size: 16px;">
  La Ciotat | Hybride
</div>
<div style="color: #484745; font-size: 16px;">•</div>
<div style="color: #484745; font-size: 16px;">
  EUR 60 000 - 90 000 | Plein temps
</div>
<!-- Benefits Highlight Row (A/B test treatment only) -->
<table><tr><td>"""
    + ("<div>Avantage offre A/B test rempli de texte de remplissage. </div>" * 60)
    + '</td></tr></table>\n<!-- CTA Link -->\n<a href="'
    + LAST_CARD_JOB_URL
    + """?kuuid=abc" style="color: #B43332;">
  Afficher l’offre d’emploi
</a>
"""
)

HTML_MARKETING = """
<p>Jean, de nouveaux postes qui valent votre temps.</p>
<a href="https://www.jobleads.com/home?kuuid=abc">Se connecter</a>
"""


def test_extracts_single_offer_with_contract_before_salary(make_msg):
    offers = extract_jobleads(HTML_SINGLE_OFFER, make_msg(), {})

    assert len(offers) == 1
    o = offers[0]
    assert o["titre"] == "Consultant DevOps"
    assert o["entreprise"] == "Les-Filles-Et-Les-Gar"
    assert o["ville"] == "Ollioules"
    assert o["type_contrat"] == "Plein temps"
    assert o["salaire_min"] == "65000"
    assert o["salaire_max"] == "90000"
    assert o["url"] == "https://www.jobleads.com/job/ed8c0008a84b8a214a020ccddb1d474f7"
    assert o["url_qualite"] == "construite"
    assert o["notes"] == "Mode de travail : Sur place"


def test_extracts_every_card_from_a_multi_offer_digest_with_salary_before_contract(make_msg):
    offers = extract_jobleads(HTML_DIGEST, make_msg(), {})

    assert len(offers) == 2

    first = offers[0]
    assert first["titre"] == "Développeur Back-End PHP H/F (F/H)"
    assert first["entreprise"] == "Synanto"
    assert first["ville"] == "Marseille"
    assert first["type_contrat"] == "Plein temps"
    assert first["salaire_min"] == "55000"
    assert first["salaire_max"] == "75000"
    assert first["url"] == "https://www.jobleads.com/job/e4d8fe5c8274fd4f47421fd46f59fe716"
    assert first["url_qualite"] == "construite"
    assert first["notes"] == "Mode de travail : Sur place"

    second = offers[1]
    assert second["titre"] == "Développeur·euse Front-end Senior"
    assert second["entreprise"] == "Smart Tribune"
    assert second["notes"] == "Mode de travail : Hybride"
    assert second["url"] == "https://www.jobleads.com/job/eb84384e47313314bfaa04b016eff2cb1"


def test_returns_empty_list_for_a_marketing_email_with_no_offer_card(make_msg):
    assert extract_jobleads(HTML_MARKETING, make_msg(), {}) == []


def test_finds_the_url_of_the_last_card_even_past_a_long_benefits_row(make_msg):
    offers = extract_jobleads(HTML_DIGEST_LAST_CARD_WITH_BENEFITS_ROW, make_msg(), {})

    assert len(offers) == 2
    last = offers[1]
    assert last["titre"] == "Cloud Automation & Platform Engineer (AWS / DevSecOps) (H/F)"
    assert last["url"] == "https://www.jobleads.com/job/e7b522d99d10b4b8aa7ee8f5df07b9485"
    assert last["url_qualite"] == "construite"
