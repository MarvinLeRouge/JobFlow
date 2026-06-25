# Job search tracker — doc

Centralise les offres d'emploi reçues par email dans des CSV importables dans Google Sheets.

---

## Structure

```
sources/
  <provider>/          ← EML classés par plateforme
    france-travail/
    indeed/
    jobijoba/
    linkedin/
    meteojob/
    talent-com/
  journal/             ← Journal.md (source one-time, remplissage manuel)
  _duplicates/         ← doublons mis en quarantaine

output/                ← CSV à importer dans Google Sheets
  offres.csv
  candidatures.csv
  entretiens.csv
  journal_quotidien.csv
  entreprises_cibles.csv

config/
  config.json          ← stack keywords, ville→dept, colonnes
  scraping_patterns.json ← patterns d'extraction par provider

logs/
  eml_index.csv        ← suivi des EML (Message-ID, statut extraction)
  extraction_history.csv

archive/               ← scripts one-shot, index obsolètes
```

---

## Workflow nominal

Quand tu reçois de nouveaux emails d'alerte :

```bash
# 1. Sauvegarder les emails en .eml dans sources/<provider>/
#    (Gmail → ⋮ → Télécharger le message)

# 2. Renommer, dédoublonner, indexer
python3 rename_eml.py

# 3. Extraire les offres vers output/offres.csv
python3 extract_eml.py
```

---

## Scripts

### `rename_eml.py`

Renomme les EML au format `yyyymmdd-hhmm-nom.eml`, détecte les doublons par Message-ID, et vérifie que chaque fichier est dans le bon dossier provider.

```bash
python3 rename_eml.py              # renommer + dédoublonner
python3 rename_eml.py --dry-run    # simulation
python3 rename_eml.py --check      # vérifier dossiers sans rien modifier
python3 rename_eml.py --purge      # vider sources/_duplicates/
```

Fichiers écrits : `logs/eml_index.csv`

---

### `extract_eml.py`

Extrait les offres de tous les EML marqués `PENDING` dans l'index.

```bash
python3 extract_eml.py             # extraire
python3 extract_eml.py --dry-run   # simulation
```

Produit deux fichiers :
- `output/offres.csv` — archive locale cumulative, utilisée pour la déduplication (ne pas réimporter dans Sheets)
- `output/import_YYYYMMDD.csv` — **nouvelles lignes du run uniquement**, à importer dans Sheets via *Données → Importer → Ajouter aux données actuelles*

Autres fichiers écrits : `logs/eml_index.csv`, `logs/extraction_history.csv`, `logs/YYYYMMDD-HHMM_extraction.log`

Providers supportés : France Travail, Indeed (alertes + match direct), LinkedIn, Meteojob, Jobijoba, Talent.com.

---

## Google Sheets — les 5 feuilles

### `offres` — toutes les offres vues

| Colonne | Notes |
|---|---|
| `ID` | `E###` (email) ou `J###` (journal, saisie manuelle) |
| `Traite` | checkbox — cocher quand l'offre est qualifiée |
| `Date_decouverte` | `YYYY-MM-DD` — trier par date |
| `Source` | France Travail, Indeed, LinkedIn… |
| `Cle_dedup` | `entreprise\|ville\|titre_court` — mise en forme conditionnelle pour détecter les doublons |
| `Doublon_ID` | ID de la première occurrence si doublon |
| `URL_qualite` | `construite` (stable) / `email` (lien tracking, peut expirer) / `vide` |
| `Stack` | tags tech séparés par virgules |
| `Statut` | voir valeurs ci-dessous |

Valeurs `Statut` : `À traiter` · `Déjà vue` · `Hors stack` · `Hors profil` · `Hors zone géo` · `Expirée` · `Douteuse/Arnaque` · `Intéressante` · `Candidature envoyée` · `En cours` · `Entretien planifié` · `Offre reçue` · `Refusée` · `Abandonnée`

---

### `candidatures` — candidatures envoyées

| Colonne | Notes |
|---|---|
| `ID_offre` | lien vers `offres.ID` |
| `Canal` | LinkedIn, Email direct, APEC, France Travail, Site entreprise… |
| `Statut` | Envoyée · En attente · Relancée · Entretien planifié · Entretien passé · Refusée · Sans réponse · Abandonnée |

---

### `entretiens`

| Colonne | Notes |
|---|---|
| `Format` | Téléphone · Visio · Présentiel |
| `Duree` | en minutes |
| `Suite` | ce qui s'est passé après |

---

### `journal_quotidien` — log d'activité

| Colonne | Notes |
|---|---|
| `Type_activite` | Recherche offres · Candidature envoyée · Entretien · Relance · Formation · Veille techno · Admin · Réseau · Autre |
| `Plateforme` | France Travail, Indeed, LinkedIn… |

---

### `entreprises_cibles` — wishlist

| Colonne | Notes |
|---|---|
| `Interet` | Faible · Moyen · Fort · Très fort |
| `Statut` | À contacter · Contactée · En discussion · Abandonnée |

---

## Ajouter un provider

1. Créer `sources/<provider>/`
2. Ajouter une entrée dans `config/scraping_patterns.json` :
   - `folder` : nom du dossier
   - `sender_domains` : domaine(s) expéditeur(s)
   - `skip: true` si l'email ne contient pas d'offres individuelles (digest, newsletter)
3. Implémenter `extract_<provider>(html, msg, patterns)` dans `extract_eml.py`
4. L'ajouter dans la table `EXTRACTORS`
5. Tester : `python3 extract_eml.py --dry-run`

---

## Tips Google Sheets

- **Trier par date** : colonne `Date_decouverte` en `YYYY-MM-DD` → tri alphabétique = tri chronologique
- **Détecter les doublons** : mise en forme conditionnelle sur `Cle_dedup` → `=NB.SI($G:$G;G2)>1`
- **Statut en couleur** : mise en forme conditionnelle sur `Statut` par valeur
- **Filtre actif** : `Traite = FALSE` + `Statut = "À traiter"` → vue de travail quotidienne
