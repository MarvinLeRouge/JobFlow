🇫🇷 Version française | [🇬🇧 English version](roadmap.md)

---

# Roadmap

**L'automatisation de l'import Sheets** a été mise en œuvre dans `sheets_sync.py` (voir le [README](../README.fr.md) principal). Les offres atterrissent désormais directement dans la feuille de suivi principale via l'API Google Sheets, protégées par un état d'erreur persistant qui bloque les synchronisations suivantes après un échec jusqu'à acquittement, ce qui referme le point que cette section décrivait auparavant comme volontairement écarté.

**Nettoyer les emails Gmail déjà traités** a été mis en œuvre dans `gmail_cleanup.py` (voir le [README](../README.fr.md) principal) : un script déclenché manuellement qui met à la corbeille les emails déjà labellisés, en recoupant avec le ledger local plutôt qu'en se fiant seulement au label Gmail.
