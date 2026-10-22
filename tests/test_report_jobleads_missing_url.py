import csv
import json

from report_jobleads_missing_url import find_offers_with_missing_url, reextract_url, run

HTML_TWO_OFFERS = """
<a href="https://www.jobleads.com/fr/job/consultant-devops--ollioules--ed8c0008a84b8a214a020ccddb1d474f7?kuuid=abc">
  <div style="color: #100F0E; font-size: 20px; font-weight: 700;">
    Consultant DevOps
  </div>
  <div style="color: #484745; font-size: 16px;">&bull; Les-Filles-Et-Les-Gar</div>
  <div style="color: #484745; font-size: 16px;">&bull; Ollioules | Sur place</div>
  <div style="color: #484745; font-size: 16px;">&bull; Plein temps | EUR 65 000 - 90 000</div>
  <td style="color: #A03E3C;">Voir tous les détails et postuler</td>
</a>
<!-- Top section -->
<div style="color: #100F0E; font-size: 20px; font-weight: 600;">
  Développeur Back-End PHP H/F
</div>
<div style="color: #272625; font-size: 16px;">Synanto</div>
<div style="color: #484745; font-size: 16px;">•</div>
<div style="color: #484745; font-size: 16px;">Marseille | Sur place</div>
<div style="color: #484745; font-size: 16px;">•</div>
<div style="color: #484745; font-size: 16px;">EUR 55 000 - 75 000 | Plein temps</div>
<a href="https://www.jobleads.com/job/e4d8fe5c8274fd4f47421fd46f59fe716?kuuid=x">
  Afficher l'offre d'emploi
</a>
"""


def _write_eml(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "From: mailer@jobleads.com\r\n"
        "Subject: Il y a 2 nouvelles offres\r\n"
        'Content-Type: multipart/alternative; boundary="BOUND"\r\n'
        "\r\n"
        "--BOUND\r\n"
        "Content-Type: text/html; charset=utf-8\r\n"
        "\r\n"
        f"{HTML_TWO_OFFERS}\r\n"
        "--BOUND--\r\n"
    )
    path.write_bytes(content.encode("utf-8"))


def _write_offres_csv(path, rows):
    headers = ["ID", "Source", "Titre", "URL", "Message_ID"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_ledger(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")


def test_find_offers_with_missing_url_keeps_only_jobleads_rows_without_url(tmp_path):
    csv_path = tmp_path / "offres.csv"
    _write_offres_csv(
        csv_path,
        [
            {"ID": "E000001", "Source": "JobLeads", "Titre": "A", "URL": "", "Message_ID": "<m1>"},
            {
                "ID": "E000002",
                "Source": "JobLeads",
                "Titre": "B",
                "URL": "https://x",
                "Message_ID": "<m1>",
            },
            {
                "ID": "E000003",
                "Source": "Jobijoba",
                "Titre": "C",
                "URL": "",
                "Message_ID": "<m2>",
            },
        ],
    )

    rows = find_offers_with_missing_url(csv_path)

    assert [r["ID"] for r in rows] == ["E000001"]


def test_reextract_url_finds_the_matching_offer_by_title(tmp_path):
    eml_path = tmp_path / "jobleads" / "raw.eml"
    _write_eml(eml_path)

    url = reextract_url(eml_path, "Développeur Back-End PHP H/F")

    assert url == "https://www.jobleads.com/job/e4d8fe5c8274fd4f47421fd46f59fe716"


def test_reextract_url_returns_none_when_no_offer_matches_the_title(tmp_path):
    eml_path = tmp_path / "jobleads" / "raw.eml"
    _write_eml(eml_path)

    assert reextract_url(eml_path, "Titre inconnu") is None


def test_run_resolves_the_eml_via_the_ledger_and_reextracts_the_url(tmp_path):
    csv_path = tmp_path / "offres.csv"
    _write_offres_csv(
        csv_path,
        [
            {
                "ID": "E010411",
                "Source": "JobLeads",
                "Titre": "Consultant DevOps",
                "URL": "",
                "Message_ID": "<m1>",
            }
        ],
    )
    sources_dir = tmp_path / "sources"
    _write_eml(sources_dir / "jobleads" / "raw.eml")
    ledger_file = tmp_path / "ledger.json"
    _write_ledger(ledger_file, {"<m1>": {"fichier": "jobleads/raw.eml"}})

    results = run(csv_path, sources_dir, ledger_file)

    assert results == [
        ("E010411", "https://www.jobleads.com/job/ed8c0008a84b8a214a020ccddb1d474f7")
    ]


def test_run_reports_none_when_the_message_id_is_not_in_the_ledger(tmp_path):
    csv_path = tmp_path / "offres.csv"
    _write_offres_csv(
        csv_path,
        [
            {
                "ID": "E010411",
                "Source": "JobLeads",
                "Titre": "Consultant DevOps",
                "URL": "",
                "Message_ID": "<missing>",
            }
        ],
    )
    ledger_file = tmp_path / "ledger.json"
    _write_ledger(ledger_file, {})

    results = run(csv_path, tmp_path / "sources", ledger_file)

    assert results == [("E010411", None)]
