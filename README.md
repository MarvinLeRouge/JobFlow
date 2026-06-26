# Job Search Tracker

Pipeline Python de traitement des alertes emploi reçues par email.  
Les offres sont extraites depuis des fichiers `.eml`, dédoublonnées, et exportées en CSV pour import dans Google Sheets.

---

## Fonctionnement général

```
sources/<provider>/   ← fichiers .eml classés par plateforme
        ↓
  rename_eml.py       ← renommage, dédup par Message-ID, indexation
        ↓
  extract_eml.py      ← extraction des offres → CSV
        ↓
output/import_YYYYMMDD.csv  ← à importer manuellement dans Google Sheets
```

---

## Scripts

### `rename_eml.py`

Renomme les fichiers `.eml` au format `yyyymmdd-hhmm-nom.eml`, détecte les doublons par Message-ID, et vérifie que chaque fichier est dans le bon dossier provider.

```bash
python3 rename_eml.py              # renommer + dédoublonner
python3 rename_eml.py --dry-run    # simulation sans modification
python3 rename_eml.py --check      # vérifier les dossiers sans rien modifier
python3 rename_eml.py --purge      # vider sources/_duplicates/
```

Fichiers écrits : `logs/eml_index.csv`

---

### `extract_eml.py`

Extrait les offres de tous les `.eml` marqués `PENDING` dans l'index, les dédoublonne, détecte la stack technique et les titres blacklistés, puis écrit deux fichiers CSV.

```bash
python3 extract_eml.py             # extraction complète
python3 extract_eml.py --dry-run   # simulation sans écriture
python3 extract_eml.py --with-headers   # forcer l'en-tête dans le CSV d'import
python3 extract_eml.py --no-headers     # forcer l'absence d'en-tête
```

Fichiers écrits :
- `output/offres.csv` — archive locale cumulative (référence dédup, **ne pas réimporter dans Sheets**)
- `output/import_YYYYMMDD.csv` — nouvelles lignes du run uniquement, à importer dans Sheets
- `logs/eml_index.csv`, `logs/extraction_history.csv`, `logs/YYYYMMDD-HHMM_extraction.log`

Providers supportés : France Travail, Indeed (alertes + match direct), LinkedIn, Meteojob, Jobijoba, Talent.com.

---

## Configuration

### `config/config.json`

| Clé | Rôle |
|-----|------|
| `offres_csv_headers` | ordre des colonnes CSV |
| `stack_keywords` | mots-clés de détection de stack technique |
| `ville_dept` | correspondance ville → numéro de département |
| `blacklist_titres` | titres à marquer automatiquement (ex : "nounou", "garde d'enfant") |

### `config/scraping_patterns.json`

Patterns d'extraction par provider : domaine expéditeur, dossier source, expressions régulières.

---

## Déduplication

La clé de dédup (`Cle_dedup`) est construite à partir de :
- l'entreprise normalisée (minuscules, sans accents ni tirets)
- la ville normalisée
- un slug du titre (sans mots vides ni mentions H/F, tronqué à 25 caractères)

Format : `entreprise|ville|titreslugtronque`

Si une offre avec la même clé existe déjà dans `offres.csv`, la colonne `Doublon_ID` est renseignée avec l'ID de la première occurrence.

---

## Blacklist de titres

Les termes définis dans `blacklist_titres` (config.json) sont recherchés dans le titre à chaque extraction, sans sensibilité à la casse ni aux accents.

Si un titre correspond :
- `Raison_exclusion` : `Blacklisté: <terme>`
- `Notes` : `⛔ Blacklisté: <terme>`

La ligne est conservée dans le CSV et importée normalement dans Sheets.

---

## Google Sheets — import et mise en forme

**Import :** Données → Importer → Ajouter à la fin de la feuille, en sélectionnant `output/import_YYYYMMDD.csv`.

**Mise en forme conditionnelle** (à configurer une fois, plage `A2:U`) :

| Priorité | Couleur | Formule | Signification |
|----------|---------|---------|---------------|
| 1 (haute) | 🟡 Jaune | `=$H2<>""` | Doublon |
| 2 | 🔴 Rouge | `=ISNUMBER(SEARCH("Blacklist";$T2))` | Blacklisté |

> Colonnes de référence (après suppression de `Statut`) : A=ID, B=Traite, C=Date_decouverte, D=Source, E=Titre, F=Entreprise, G=Cle_dedup, H=Doublon_ID, I=Ville, J=Dept, K=Type_contrat, L=Salaire_min, M=Salaire_max, N=URL, O=URL_qualite, P=URL_redirect, Q=Stack, R=Raison_exclusion, S=Date_candidature, T=Notes

---

## Ajouter un provider

1. Créer `sources/<provider>/`
2. Ajouter une entrée dans `config/scraping_patterns.json`
3. Implémenter `extract_<provider>(html, msg, patterns)` dans `extract_eml.py`
4. L'ajouter dans la table `EXTRACTORS`
5. Tester : `python3 extract_eml.py --dry-run`
