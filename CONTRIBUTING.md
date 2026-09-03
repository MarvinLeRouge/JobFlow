[🇫🇷 Version française](CONTRIBUTING.fr.md) | 🇬🇧 English version

---

# Contributing

This is a personal project, but external contributions (bug reports, fixes, small improvements) are welcome.

## Prerequisites

- Python 3.13
- A Google Cloud project with the Gmail API and Google Sheets API enabled, if you intend to run the pipeline for real (see [docs/setup_gmail_auth.md](docs/setup_gmail_auth.md)). Not required to run the test suite.

## Local setup

```bash
git clone https://github.com/MarvinLeRouge/JobFlow.git
cd JobFlow
pip install -r requirements.txt
pip install -r requirements-dev.txt
pre-commit install   # once, to enable the git hook
```

## Running tests

```bash
pytest
ruff check .
ruff format --check .
```

All three must pass before opening a pull request.

## Workflow

1. Fork the repository and create a branch off `main`.
2. Make your change, with tests covering it (see the [Testing](README.md#testing) section of the README).
3. Commit following the convention below.
4. Push and open a pull request against `main`.
5. CI must pass before review.

### Branch naming

| Type | Prefix |
|---|---|
| Feature | `feat/short-description` |
| Bug fix | `fix/short-description` |
| Chore | `chore/short-description` |
| Documentation | `docs/short-description` |
| Refactor | `refactor/short-description` |
| Tests | `test/short-description` |

### Commit convention

[Conventional Commits](https://www.conventionalcommits.org/), imperative mood, lowercase summary, no trailing period, with a mandatory `Modified files:` list:

```
fix(extract): skip talent.com footer titles before ID assignment

Modified files:
- extract/providers/talent_com.py - add TALENT_COM_FOOTER_TITLES, skip before offer dict creation
- tests/extract/providers/test_talent_com.py - cover the new skip
```

### Code style

- Python: [Ruff](https://docs.astral.sh/ruff/) for linting and formatting, enforced by `pre-commit` and CI
- Tests: `pytest`, mirroring the source structure under `tests/`

## Code of Conduct

This project follows a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold it.

## License

By contributing, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
