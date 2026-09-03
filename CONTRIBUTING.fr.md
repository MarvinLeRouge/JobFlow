🇫🇷 Version française | [🇬🇧 English version](CONTRIBUTING.md)

---

# Contribuer

Ceci est un projet personnel, mais les contributions externes (signalement de bugs, corrections, petites améliorations) sont les bienvenues.

## Prérequis

- Python 3.13
- Un projet Google Cloud avec les API Gmail et Google Sheets activées, si vous comptez faire tourner le pipeline pour de vrai (voir [docs/setup_gmail_auth.fr.md](docs/setup_gmail_auth.fr.md)). Non nécessaire pour lancer la suite de tests.

## Installation locale

```bash
git clone https://github.com/MarvinLeRouge/JobFlow.git
cd JobFlow
pip install -r requirements.txt
pip install -r requirements-dev.txt
pre-commit install   # une fois, pour activer le hook git
```

## Lancer les tests

```bash
pytest
ruff check .
ruff format --check .
```

Les trois doivent passer avant d'ouvrir une pull request.

## Workflow

1. Forker le dépôt et créer une branche à partir de `main`.
2. Faire la modification, avec des tests la couvrant (voir la section [Tests](README.fr.md#tests) du README).
3. Committer en suivant la convention ci-dessous.
4. Pousser et ouvrir une pull request contre `main`.
5. La CI doit passer avant relecture.

### Nommage des branches

| Type | Préfixe |
|---|---|
| Fonctionnalité | `feat/description-courte` |
| Correction de bug | `fix/description-courte` |
| Tâche annexe | `chore/description-courte` |
| Documentation | `docs/description-courte` |
| Refactorisation | `refactor/description-courte` |
| Tests | `test/description-courte` |

### Convention de commit

[Conventional Commits](https://www.conventionalcommits.org/), à l'impératif, résumé en minuscules, sans point final, avec une liste `Modified files:` obligatoire :

```
fix(extract): skip talent.com footer titles before ID assignment

Modified files:
- extract/providers/talent_com.py - add TALENT_COM_FOOTER_TITLES, skip before offer dict creation
- tests/extract/providers/test_talent_com.py - cover the new skip
```

Note : le message de commit lui-même reste en anglais, y compris pour ce dépôt (voir la convention du projet), seule cette page d'instructions est traduite.

### Style de code

- Python : [Ruff](https://docs.astral.sh/ruff/) pour le lint et le formatage, appliqué par `pre-commit` et la CI
- Tests : `pytest`, en miroir de la structure du code source sous `tests/`

## Code de conduite

Ce projet suit un [Code de conduite](CODE_OF_CONDUCT.fr.md). En y participant, vous êtes tenu de le respecter.

## Licence

En contribuant, vous acceptez que vos contributions soient placées sous la [licence MIT](LICENSE) du projet.
