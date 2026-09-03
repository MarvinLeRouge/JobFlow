🇫🇷 Version française | [🇬🇧 English version](SECURITY.md)

---

# Politique de sécurité

## Versions supportées

Ce projet n'a pas de branche de version maintenue : seul l'état le plus récent de `main` est supporté.

## Signaler une vulnérabilité

Merci de signaler les vulnérabilités de sécurité via le signalement privé de vulnérabilités de GitHub : rendez-vous dans l'onglet [Security](https://github.com/MarvinLeRouge/JobFlow/security) de ce dépôt et cliquez sur "Report a vulnerability". N'ouvrez pas d'issue publique pour un signalement de sécurité.

Ce projet personnel n'a qu'un seul mainteneur : les délais de réponse sont du mieux possible, mais les signalements seront pris en compte et examinés aussi vite que possible.

## Périmètre

Dans le périmètre : le code du pipeline Python de ce dépôt (`fetch_gmail.py`, `rename_eml.py`, `extract_eml.py`, `sheets_sync.py`, `gmail_labeling.py`, `gmail_cleanup.py`, `run_pipeline.py`, et le package `extract/`) et sa gestion de la configuration.

Hors périmètre : les services tiers intégrés (API Gmail, API Google Sheets, OpenStreetMap Nominatim) - signalez les vulnérabilités de ces services directement à leurs éditeurs respectifs.
