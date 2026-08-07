# Job Search Tracker

Pipeline Python de traitement des alertes emploi reçues par email.
Les offres sont récupérées depuis Gmail, extraites des fichiers `.eml`, dédoublonnées, puis exportées en CSV pour import dans Google Sheets.

---

## Fonctionnement général

```
fetch_gmail.py        ← récupération via l'API Gmail, OAuth2, routage vers sources/<provider>/
        ↓
sources/<provider>/   ← fichiers .eml classés par plateforme
        ↓
  rename_eml.py       ← renommage, dédup par Message-ID, indexation dans le ledger
        ↓
  extract_eml.py      ← extraction des offres → CSV
        ↓
output/import_YYYYMMDD.csv  ← à importer manuellement dans Google Sheets
```

`run_pipeline.py` enchaîne les trois étapes et constitue le point d'entrée recommandé.

---

## Scripts

### `fetch_gmail.py`

Interroge l'API Gmail pour récupérer les nouvelles alertes, les route vers `sources/<provider>/`, et enregistre chaque email dans `logs/email_ledger.json`.

```bash
python3 fetch_gmail.py                  # récupérer les nouveaux emails
python3 fetch_gmail.py --dry-run        # simulation, sans téléchargement ni écriture
python3 fetch_gmail.py --since-days 30  # premier run uniquement : emails des 30 derniers jours
```

`--since-days` n'est nécessaire que pour le tout premier run, quand le ledger n'a encore aucun historique de fetch. Les runs suivants déterminent automatiquement leur date de départ à partir du `fetched_at` le plus récent du ledger, avec une marge de sécurité pour ne rien perdre entre deux runs.

Nécessite une configuration OAuth2 Gmail préalable (une seule fois), voir `docs/setup_gmail_auth.md`.

Fichiers écrits : fichiers `.eml` dans `sources/<provider>/`, `logs/email_ledger.json`.

---

### `rename_eml.py`

Renomme les fichiers `.eml` au format `yyyymmdd-hhmm-nom.eml`, détecte les doublons par Message-ID, et vérifie que chaque fichier est dans le bon dossier provider.

```bash
python3 rename_eml.py              # renommer + dédoublonner
python3 rename_eml.py --dry-run    # simulation sans modification
python3 rename_eml.py --check      # vérifier les dossiers sans rien modifier
python3 rename_eml.py --purge      # vider sources/_duplicates/
```

Fichiers écrits : `logs/email_ledger.json`.

---

### `extract_eml.py`

Extrait les offres de tous les `.eml` marqués `PENDING` dans le ledger, les dédoublonne, détecte la stack technique et les titres blacklistés, puis écrit deux fichiers CSV.

```bash
python3 extract_eml.py             # extraction complète
python3 extract_eml.py --dry-run   # simulation sans écriture
python3 extract_eml.py --with-headers   # forcer l'en-tête dans le CSV d'import
python3 extract_eml.py --no-headers     # forcer l'absence d'en-tête
```

Fichiers écrits :
- `output/offres.csv` - archive locale cumulative (référence dédup, **ne pas réimporter dans Sheets**)
- `output/import_YYYYMMDD.csv` - nouvelles lignes du run uniquement, à importer dans Sheets
- `logs/email_ledger.json`, `logs/extraction_history.csv`, `logs/YYYYMMDD-HHMM_extraction.log`

Providers supportés : France Travail, Indeed (alertes + match direct), LinkedIn, Meteojob, Jobijoba, Talent.com.

---

### `run_pipeline.py`

Point d'entrée recommandé. Enchaîne `fetch_gmail` → `rename_eml` → `extract_eml`.

```bash
python3 run_pipeline.py            # pipeline complet
python3 run_pipeline.py --dry-run  # simuler les trois étapes
```

Fail-fast : le pipeline s'arrête à la première étape qui échoue, pour qu'une étape suivante ne s'exécute jamais sur un état laissé incohérent par une étape précédente.

---

## Configuration OAuth2 Gmail

`fetch_gmail.py` nécessite un projet Google Cloud avec l'API Gmail activée et une autorisation OAuth2 réalisée une seule fois (`credentials.json` et `token.json`, tous deux exclus du dépôt). Voir `docs/setup_gmail_auth.md` pour le pas-à-pas complet, y compris le piège de l'erreur "Access blocked" en mode test et la vérification du rafraîchissement silencieux du token.

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

## Le ledger (`logs/email_ledger.json`)

Fichier de suivi partagé entre `fetch_gmail.py`, `rename_eml.py` et `extract_eml.py`, qui remplace l'ancien `logs/eml_index.csv`. C'est un unique objet JSON indexé par Message-ID, une entrée par email :

```json
{
  "<msg-1@example.com>": {
    "gmail_id": "18f2a9c7b3e4d501",
    "fichier": "indeed/20260806-1032-foo.eml",
    "date_email": "2026-08-06T10:32:00+0200",
    "fetched_at": "2026-08-06T10:35:12Z",
    "indexed_at": "2026-08-06T10:35:12Z",
    "statut_extraction": "PENDING"
  }
}
```

- `gmail_id` : l'ID du message côté API Gmail. `"before_gmail_api"` pour les entrées issues de la migration depuis l'ancien `eml_index.csv`, `"manual"` pour les fichiers indexés par `rename_eml.py` sans jamais avoir été récupérés via l'API (déposés à la main dans `sources/`).
- `fichier` : chemin du fichier relatif à `sources/`.
- `date_email` : l'en-tête `Date` de l'email, converti en timestamp ISO 8601 avec décalage horaire.
- `fetched_at` : timestamp UTC du téléchargement par `fetch_gmail.py`, vide pour les entrées antérieures à la migration.
- `indexed_at` : timestamp UTC du dernier passage de `rename_eml.py` sur ce fichier.
- `statut_extraction` : `PENDING`, `OK`, `PARTIEL`, `ERREUR` ou `IGNORE`, renseigné par `extract_eml.py` une fois le fichier traité.

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

## Google Sheets - import et mise en forme

**Import :** Données → Importer → Ajouter à la fin de la feuille, en sélectionnant `output/import_YYYYMMDD.csv`.

**Mise en forme conditionnelle** (à configurer une fois, plage `A2:U`) :

| Priorité | Couleur | Formule | Signification |
|----------|---------|---------|---------------|
| 1 (haute) | 🟡 Jaune | `=$H2<>""` | Doublon |
| 2 | 🔴 Rouge | `=ISNUMBER(SEARCH("Blacklist";$T2))` | Blacklisté |

> Colonnes de référence : A=ID, B=Traite, C=Date_decouverte, D=Source, E=Titre, F=Entreprise, G=Cle_dedup, H=Doublon_ID, I=Ville, J=Dept, K=Type_contrat, L=Salaire_min, M=Salaire_max, N=URL, O=URL_qualite, P=URL_redirect, Q=Stack, R=Raison_exclusion, S=Date_candidature, T=Notes, U=Message_ID
>
> Les colonnes A à T n'ont pas changé depuis avant l'intégration Gmail. `Message_ID` a été ajoutée en dernière position (U) plutôt qu'insérée, pour que les formules de mise en forme conditionnelle ci-dessus (et toute autre formule référençant une colonne par sa lettre) continuent de fonctionner sans modification.

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
ruff format --check .
pre-commit install   # une seule fois, pour activer le hook git
```

---

## Ajouter un provider

1. Créer `sources/<provider>/`
2. Ajouter une entrée dans `config/scraping_patterns.json`
3. Implémenter `extract_<provider>(html, msg, patterns)` dans `extract_eml.py`
4. L'ajouter dans la table `EXTRACTORS`
5. Tester : `python3 extract_eml.py --dry-run`

---

## Roadmap

**L'automatisation de l'import Sheets** a été envisagée puis volontairement écartée pour l'instant : écrire les offres directement via l'API Google Sheets, plutôt que par l'import CSV manuel, nécessiterait un nouveau scope OAuth `spreadsheets`, la gestion d'écritures partielles sur un document partagé en direct, et ferait disparaître le filet de sécurité que constitue la relecture visuelle avant que les offres n'atterrissent dans la feuille de suivi principale. Ce point reste hors périmètre pour l'instant, à reconsidérer une fois la confiance dans la qualité de l'extraction automatique établie dans la durée : un projet à part entière, pas une tâche en attente sur celui-ci.
