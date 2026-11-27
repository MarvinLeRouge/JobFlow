🇫🇷 Version française | [🇬🇧 English version](roadmap.md)

---

# Roadmap

**L'automatisation de l'import Sheets** a été mise en œuvre dans `sheets_sync.py` (voir le [README](../README.fr.md) principal). Les offres atterrissent désormais directement dans la feuille de suivi principale via l'API Google Sheets, protégées par un état d'erreur persistant qui bloque les synchronisations suivantes après un échec jusqu'à acquittement, ce qui referme le point que cette section décrivait auparavant comme volontairement écarté.

**Nettoyer les emails Gmail déjà traités** a été mis en œuvre dans `gmail_cleanup.py` (voir le [README](../README.fr.md) principal) : un script déclenché manuellement qui met à la corbeille les emails déjà labellisés, en recoupant avec le ledger local plutôt qu'en se fiant seulement au label Gmail.

## Section 1 - Maintenance

- [x] CHORE-001 - Migrer vers uv et Python 3.14, ajouter Dependabot
- [x] CI-001 - Lancer la CI sur la PR du bot changelog pour que son auto-merge aboutisse
- [x] TEST-001 - Combler les trous de couverture par fichier
- [x] CI-002 - Épingler chaque GitHub Action sur sa majeure actuelle par SHA de commit, workflow changelog sur Node 26, aligner la config Dependabot (groupe actions unique)
- [x] CI-003 - Exclure le projet lui-même de l'export pip-audit (--no-emit-project)
- [x] CI-004 - Relever le seuil de couverture de 80 % à 85 % (seuils et docs)
- [x] CI-005 - Analyser les modifications indexées avec gitleaks dans le hook pre-commit
- [x] CHORE-002 - Vérifier les types avec mypy dans le hook pre-commit (12 erreurs de typage corrigées)
- [x] DOCS-001 - Rédiger le contexte produit (pipeline d'alertes emploi et suivi des candidatures)
