🇫🇷 Version française | [🇬🇧 English version](README.md)

---

# 🎯 JobFlow

> *Un pipeline Python qui transforme des alertes emploi dispersées en un Google Sheet unique, dédoublonné, filtré et toujours à jour — du fetch Gmail à la feuille de suivi synchronisée.*

![Status](https://img.shields.io/badge/Status-Production-brightgreen)
![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-185%20passants-brightgreen)
![License](https://img.shields.io/github/license/MarvinLeRouge/JobFlow?cacheSeconds=3600)

---

Pipeline Python de traitement des alertes emploi reçues par email.
Les offres sont récupérées depuis Gmail, extraites des fichiers `.eml`, dédoublonnées, puis synchronisées dans Google Sheets.

Voir [ARCHITECTURE.fr.md](ARCHITECTURE.fr.md) pour les choix de conception derrière le pipeline, la stratégie de dédup et les parseurs providers.

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
output/import_YYYYMMDD.csv  ← nouvelles offres du run, toujours produit
        ↓
  sheets_sync.py      ← ajoute les nouvelles lignes dans la Sheet, reproduit la mise en forme
        ↓
  Google Sheet         ← feuille de suivi principale
```

`run_pipeline.py` enchaîne les quatre étapes et constitue le point d'entrée recommandé.

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

Extrait les offres de tous les `.eml` marqués `PENDING` dans le ledger, les dédoublonne, détecte la stack technique et les titres blacklistés, puis écrit deux fichiers CSV. `extract_eml.py` lui-même est un point d'entrée fin ; le parsing/filtrage/I-O vit dans le package `extract/` (`extract/providers/` pour les parseurs HTML par provider, `extract/filters.py` pour dédup/blacklist/stack, `extract/geo.py` pour la résolution ville→département, `extract/io.py` pour l'écriture CSV/logs).

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

### `sheets_sync.py`

Synchronise les nouvelles offres du dernier `output/import_YYYYMMDD.csv` vers la vraie feuille Google Sheets : compare l'ID d'offre le plus élevé déjà présent dans la feuille (colonne A) avec le CSV pour ne retenir que les lignes qu'elle n'a pas encore, les ajoute, reproduit la formule/liste déroulante de la colonne B (`Traite`) et la liste déroulante de la colonne R (`Raison_exclusion`) sur ces lignes en copiant la mise en forme depuis l'onglet dédié "Références", puis étend les règles de mise en forme conditionnelle au niveau des lignes (surlignage doublon/blacklist/alternance, statut "En cours" en colonne A) pour couvrir les lignes nouvellement ajoutées.

```bash
python3 sheets_sync.py             # synchroniser les nouvelles lignes vers la Sheet
python3 sheets_sync.py --dry-run   # simulation, sans écriture, indique juste ce qui serait synchronisé
python3 sheets_sync.py --ack-error # acquitter et effacer un état d'erreur bloquant
```

Il ne regarde que le `output/import_YYYYMMDD.csv` du **jour même**. Si `extract_eml.py` n'en a pas produit un aujourd'hui, il affiche un message et se termine sans erreur.

**Verrou d'erreur :** en cas d'échec, le message d'erreur et l'horodatage sont enregistrés dans `logs/sheets_sync_error.json`. Chaque run suivant de `sheets_sync.py` ou de `run_pipeline.py` s'arrête alors immédiatement avec ce message, jusqu'à acquittement via `python3 sheets_sync.py --ack-error`. `fetch_gmail.py`, `rename_eml.py` et `extract_eml.py` ne sont pas affectés par ce verrou et restent utilisables individuellement.

Fichiers écrits : rien de durable en local à part `logs/sheets_sync_error.json` en cas d'échec ; la feuille elle-même est la seule sortie persistante.

---

### `sheets_sync_recovery.py`

Déclenchement manuel uniquement - jamais appelé par `run_pipeline.py`. Comme `sheets_sync.py` ne regarde que le CSV d'import du **jour même** (voir ci-dessus), un échec non acquitté un jour donné suivi d'un run normal un jour plus tard laisse silencieusement les lignes de ce jour-là orphelines pour toujours : elles ne sont jamais resynchronisées, et le suivi du "plus haut ID" de la feuille les a déjà dépassées, donc rien en aval ne remarque le trou de lui-même. Ce script détecte et répare exactement ce cas.

```bash
python3 sheets_sync_recovery.py --dry-run   # rapport seul, aucune écriture
python3 sheets_sync_recovery.py             # rattrape ce qui est trouvé
```

Compare chaque ID d'offre de la colonne A de la feuille avec `output/offres.csv` (l'archive locale cumulative, censée être parfaitement continue en ID depuis `E000001`) pour trouver tout ID manquant dans la feuille - trou interne ou queue en retard, même détection dans les deux cas. Chaque séquence continue manquante est ajoutée à la fin actuelle de la feuille, précédée d'une ligne vide en séparateur pour qu'un lot rattrapé reste visuellement distinguable d'une synchro normale du jour. La colonne A se retrouve brièvement hors ordre numérique strict après un rattrapage (purement cosmétique - rien en aval ne dépend de l'ordre ; à réordonner à la main si souhaité).

Si `output/offres.csv` elle-même a un trou, c'est une anomalie différente et plus grave - le script refuse de deviner et lève une exception plutôt que d'essayer de la corriger.

Sûr à relancer après une interruption (par ex. en cas de dépassement du quota d'écriture par minute de l'API Sheets en plein rattrapage d'un gros volume) : il relit l'état réel de la feuille au début de chaque run, donc les séquences déjà écrites cessent simplement d'apparaître comme manquantes.

---

### `run_pipeline.py`

Point d'entrée recommandé. Enchaîne `fetch_gmail` → `rename_eml` → `extract_eml` → `sheets_sync` → `gmail_labeling`.

```bash
python3 run_pipeline.py                  # pipeline complet
python3 run_pipeline.py --dry-run        # simuler les cinq étapes
python3 run_pipeline.py --since-days 30  # premier run, aucun historique de fetch
```

`--since-days` est transmis à `fetch_gmail.py`. Il est nécessaire pour le tout premier run, avant qu'aucune entrée de ledger n'existe : sans lui, le run s'arrête sur "impossible de déterminer un point de départ".

Fail-fast : le pipeline s'arrête à la première étape qui échoue, pour qu'une étape suivante ne s'exécute jamais sur un état laissé incohérent par une étape précédente. Il s'arrête aussi avant l'étape 1 si `sheets_sync.py` porte une erreur non acquittée d'un run précédent (voir le verrou d'erreur ci-dessus).

Le périmètre de l'étape `gmail_labeling` est capturé *avant* que `extract_eml` ne s'exécute (les entrées `PENDING` du ledger à ce moment-là), pas recalculé après coup - donc elle n'agit jamais que sur le delta de ce run, jamais un balayage rétroactif de tout le ledger.

---

### `gmail_labeling.py`

Marque les emails nouvellement traités par ce run comme lus, leur applique le label Gmail `Recherche emploi`, et les archive (retire le label `INBOX`) - une simple tâche de rangement, aucune suppression. Appelé automatiquement en dernière étape de `run_pipeline.py` ; pas prévu pour être lancé seul.

Nécessite son propre token OAuth2, `token_gmail_modify.json` (non versionné), avec le scope plus large `gmail.modify` (le reste du pipeline n'avait jamais eu besoin que de `gmail.readonly`). Le premier run réel ouvre un navigateur pour un écran de consentement unique.

Volontairement restreint dans ses actions, vu tout ce que `gmail.modify` autorise techniquement : le seul appel à l'API Gmail que fait ce module est `messages.modify` avec un corps figé (`addLabelIds`/`removeLabelIds`, rien de contrôlable par l'appelant hormis l'ID du label lui-même) - jamais `trash`, `delete`, `batchDelete`, ni `send`. Un plafond de sécurité (`MAX_MESSAGES_PER_RUN`, 200) refuse de continuer si la liste de messages est invraisemblablement grande pour le delta d'une journée, ce qui protège contre un bug d'appelant plutôt qu'un vrai lot légitime. Supprimer les anciens emails déjà labellisés est hors périmètre de ce module - voir `gmail_cleanup.py` ci-dessous.

**Se remettre d'un plantage du pipeline survenu après le succès d'`extract_eml`** (ex : `sheets_sync` ou `gmail_labeling` qui échoue sur un token OAuth expiré, voir [Configuration OAuth2](docs/operations.fr.md#configuration-oauth2)) : le delta de cette étape est un instantané des entrées `PENDING` du ledger pris juste avant l'exécution d'`extract_eml`, recalculé à chaque appel de `run_pipeline.py`. Si `extract_eml` a déjà fait passer ces entrées à `OK`/`PARTIEL` avant le plantage, un simple relancement de `run_pipeline.py` ne les reprendra pas pour `gmail_labeling` - elles ne sont plus `PENDING`. Il faut les rattraper manuellement :

```bash
python3 -c "
import json
from datetime import date
with open('logs/email_ledger.json') as f:
    ledger = json.load(f)
today = date.today().isoformat()
ids = [mid for mid, e in ledger.items() if e.get('fetched_at','').startswith(today) and e.get('statut_extraction') not in (None, 'PENDING')]
import gmail_labeling
gmail_labeling.run(ids, dry_run=True)  # retirer dry_run une fois le compte vérifié
"
```

---

### `gmail_cleanup.py`

Déclenché manuellement uniquement - jamais appelé par `run_pipeline.py` ni `login_pipeline_check.py`. Met à la corbeille les emails déjà labellisés (`Recherche emploi`), mais seulement ceux que le ledger local confirme avoir été réellement traités par ce pipeline.

```bash
python3 gmail_cleanup.py --dry-run
python3 gmail_cleanup.py
```

Le label Gmail seul n'est jamais un signal de suppression fiable : le script trouve les candidats en cherchant le label, puis croise cette liste avec les `gmail_id` connus du ledger avant de supprimer quoi que ce soit, car ce label existait déjà avant ce pipeline et sert aussi à classer de vraies candidatures à la main. Les entrées `statut_extraction == "ERREUR"` sont volontairement exclues de l'ensemble "traité connu" - l'extraction a réellement échoué pour elles, donc elles restent labellisées et visibles jusqu'à résolution manuelle plutôt que d'être nettoyées automatiquement.

Utilise `messages.trash` (récupérable 30 jours), jamais de suppression définitive. Naturellement idempotent : Gmail exclut les emails déjà à la corbeille des résultats de recherche par label, donc un second passage ne trouve plus rien à faire, aucun état séparé à suivre.

Remarque : le compteur de label dans l'interface Gmail affiche le nombre de conversations (threads), pas le nombre de messages individuels - le script, lui, rapporte toujours des comptes de messages, donc les deux chiffres peuvent légitimement différer si un candidat partage un fil avec d'autres messages.

---

### `login_pipeline_check.py`

Couche de confort optionnelle au-dessus de `run_pipeline.py` : propose de lancer le pipeline une fois par jour calendaire (pas une fenêtre stricte de 24h), pensée pour être déclenchée automatiquement au login graphique plutôt que lancée à la main.

Deux étapes, le même script pour les deux :

```bash
python3 login_pipeline_check.py           # lancé par l'autostart, sans terminal attaché
python3 login_pipeline_check.py --prompt  # lancé par l'étape ci-dessus, dans un terminal
```

Sans `--prompt`, il vérifie `logs/last_pipeline_check.json` (un marqueur dédié, pas le ledger de fetch - une journée sans nouvel email ne met jamais à jour `fetched_at` du ledger, ce qui casserait un test "une fois par jour") et ne fait rien si la vérification du jour a déjà eu lieu. Sinon, il se relance lui-même dans un terminal via `x-terminal-emulator` (l'alternative générique Debian) avec `--prompt`, qui demande directement à l'utilisateur et lance `run_pipeline.py` (via le `.venv` du projet) en cas de confirmation. Le marqueur est mis à jour quelle que soit la réponse, donc il ne redemandera pas avant le prochain jour calendaire.

**Configuration locale one-time** (non gérée par ce dépôt) : voir [Autostart](docs/operations.fr.md#autostart-vérification-déclenchée-au-login) dans la doc d'exploitation.

---

### `inspect_sheet_formatting.py`

Outil de diagnostic ponctuel construit pendant le spike de faisabilité de `sheets_sync.py`, ne fait pas partie du pipeline habituel. Affiche les formules de cellules, les règles de validation des données et la mise en forme conditionnelle d'une feuille, lues directement via l'API Sheets, pour inspecter précisément ce qui doit être reproduit.

```bash
python3 inspect_sheet_formatting.py <spreadsheet_id> <sheet_name>
```

À utiliser uniquement sur une feuille **de test** dupliquée, jamais en production. Fichiers écrits : aucun, affichage sur la sortie standard.

---

## Exploitation

Configuration OAuth2 (Gmail, Sheets, étiquetage Gmail), autostart, et récupération après échec de synchronisation : voir [docs/operations.fr.md](docs/operations.fr.md).

---

## Configuration

### `config/config.json`

| Clé | Rôle |
|-----|------|
| `offres_csv_headers` | ordre des colonnes CSV |
| `stack_keywords` | mots-clés de détection de stack technique |
| `ville_dept` | correspondance ville → numéro de département |
| `blacklist_titres` | titres à marquer automatiquement (ex : "nounou", "garde d'enfant") |
| `sheets_sync` | cible de synchronisation Sheets et coordonnées des cellules de référence, voir ci-dessous |

#### `sheets_sync`

| Clé | Rôle |
|-----|------|
| `spreadsheet_id` | ID de la feuille Google Sheets cible (visible dans son URL) - voir note ci-dessous |
| `sheet_name` | nom de l'onglet contenant les offres (ex : `Offres`) |
| `reference_sheet_name` | onglet contenant les cellules de référence dont `sheets_sync.py` copie la mise en forme (ex : `Références`) |
| `reference_row_b` | numéro de ligne dans l'onglet de référence contenant la formule/liste déroulante de la colonne B (`Traite`) à copier |
| `reference_row_r` | numéro de ligne dans l'onglet de référence contenant la liste déroulante de la colonne R (`Raison_exclusion`) à copier |

> `spreadsheet_id` n'est **pas** renseigné dans `config/config.json` (laissé vide, pour que ce fichier reste sans risque à committer). L'ID réel vit dans `config/config.local.json` (non versionné, fusionné par-dessus `config.json` par `sheets_sync.load_config()`), il ne se retrouve donc jamais dans l'historique git. Copier `config/config.local.json.example` vers `config/config.local.json` et y renseigner l'ID réel pour démarrer.

#### Important : l'onglet Références est une dépendance active

L'onglet `reference_sheet_name` n'est pas une aide de configuration ponctuelle : `sheets_sync.py` lit `reference_row_b` et `reference_row_r` à **chaque synchronisation**, pas une seule fois, et copie leur mise en forme sur chaque ligne nouvellement ajoutée. C'est parce que les couleurs des listes déroulantes/validations se sont révélées illisibles via l'API Sheets, la copie en direct depuis ces deux cellules de référence est donc le seul moyen de les reproduire.

Rien ne protège la structure de cet onglet. Réordonner les lignes qu'il contient (par exemple insérer une ligne au-dessus de la ligne 2), ou effacer/modifier la mise en forme ou la validation des listes déroulantes sur les cellules de référence elles-mêmes, fait que chaque synchronisation future copiera silencieusement une mise en forme incorrecte ou absente sur les nouvelles lignes - sans erreur et sans déclenchement du verrou d'erreur. Le verrou d'erreur ne détecte que le renommage ou la suppression pure et simple de l'onglet, pas un changement de sa structure interne.

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
- `fetched_at` : timestamp UTC du téléchargement par `fetch_gmail.py`. Pour les entrées migrées depuis l'ancien `eml_index.csv`, il prend la même valeur que `indexed_at` (colonne `Date_indexation` d'origine), il n'est pas vide.
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

**Import :** désormais automatisé par `sheets_sync.py` (voir ci-dessus). L'import manuel (Données → Importer → Ajouter à la fin de la feuille, en sélectionnant `output/import_YYYYMMDD.csv`) n'est plus le chemin normal, mais reste utilisable en secours si `sheets_sync.py` est bloqué ou indisponible.

**Mise en forme conditionnelle** (configurée une fois sur la feuille, plage `A2:U`) :

| Priorité | Couleur | Formule | Signification |
|----------|---------|---------|---------------|
| 1 (haute) | 🟡 Jaune | `=$H2<>""` | Doublon |
| 2 | 🔴 Rouge | `=ISNUMBER(SEARCH("Blacklist";$T2))` | Blacklisté |

> Colonnes de référence : A=ID, B=Traite, C=Date_decouverte, D=Source, E=Titre, F=Entreprise, G=Cle_dedup, H=Doublon_ID, I=Ville, J=Dept, K=Type_contrat, L=Salaire_min, M=Salaire_max, N=URL, O=URL_qualite, P=URL_redirect, Q=Stack, R=Raison_exclusion, S=Date_candidature, T=Notes, U=Message_ID
>
> Les colonnes A à T n'ont pas changé depuis avant l'intégration Gmail. `Message_ID` a été ajoutée en dernière position (U) plutôt qu'insérée, pour que les formules de mise en forme conditionnelle ci-dessus (et toute autre formule référençant une colonne par sa lettre) continuent de fonctionner sans modification.
>
> La feuille porte aussi deux autres règles au niveau des lignes non détaillées ici (surlignage alternance/stage et surlignage du statut "En cours", ce dernier limité à la colonne A). `sheets_sync.py` étend automatiquement la plage de lignes des quatre règles quand il ajoute de nouvelles lignes, en conservant la portée de colonnes propre à chacune.

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
3. Implémenter `extract_<provider>(html, msg, patterns)` dans un nouveau `extract/providers/<provider>.py`
4. L'importer et l'ajouter dans la table `EXTRACTORS` de `extract/providers/__init__.py`
5. Ajouter des tests dans `tests/extract/providers/test_<provider>.py`
6. Tester : `python3 extract_eml.py --dry-run`

---

## Roadmap

Voir [docs/roadmap.fr.md](docs/roadmap.fr.md).

---

## À propos

Projet personnel à double objectif :

- **Répondre à un besoin réel** — centraliser des alertes emploi dispersées entre six providers et jusqu'à une dizaine d'emails par jour dans un Google Sheet unique, dédoublonné, filtré et toujours à jour
- **Portfolio** — démontre un pipeline structuré et testé : intégrations OAuth2 (Gmail + Sheets), parsing HTML par regex par provider, déduplication cross-provider, et un verrou d'erreur persistant qui protège la feuille de production contre les synchronisations partielles

---

## 🛠️ Stack technique

| Couche | Technologie |
|---|---|
| Langage | ![Python](https://img.shields.io/badge/Python_3.13-3776AB?logo=python&logoColor=white&style=flat-square) |
| Fetch email | ![Gmail API](https://img.shields.io/badge/Gmail_API-EA4335?logo=gmail&logoColor=white&style=flat-square) OAuth2 |
| Sync feuille | ![Google Sheets API](https://img.shields.io/badge/Google_Sheets_API-34A853?logo=googlesheets&logoColor=white&style=flat-square) |
| Géocodage fallback | ![OpenStreetMap](https://img.shields.io/badge/Nominatim_(OSM)-7EBC6F?logo=openstreetmap&logoColor=white&style=flat-square) |
| Tests | ![pytest](https://img.shields.io/badge/pytest-0A9EDC?logo=pytest&logoColor=white&style=flat-square) — 185 tests |
| Linting | ![Ruff](https://img.shields.io/badge/Ruff-D7FF64?logo=ruff&logoColor=black&style=flat-square) |
| Pre-commit | ![pre-commit](https://img.shields.io/badge/pre--commit-FAB040?logo=precommit&logoColor=black&style=flat-square) |

---

## Licence

[MIT](LICENSE)
