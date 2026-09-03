🇫🇷 Version française | [🇬🇧 English version](operations.md)

---

# Exploitation

Tâches d'exploitation courantes pour faire tourner ce pipeline sur sa propre machine : pas une référence de code (voir le [README](../README.fr.md) principal pour ça), mais des procédures de mise en place et de récupération.

## Configuration OAuth2

**Gmail :** `fetch_gmail.py` nécessite un projet Google Cloud avec l'API Gmail activée et une autorisation OAuth2 réalisée une seule fois (`credentials.json` et `token.json`, tous deux exclus du dépôt). Voir [docs/setup_gmail_auth.md](setup_gmail_auth.md) pour le pas-à-pas complet (actuellement disponible en anglais uniquement), y compris le piège de l'erreur "Access blocked" en mode test et la vérification du rafraîchissement silencieux du token.

**Google Sheets :** `sheets_sync.py` a besoin de son propre token OAuth2, `token_sheets.json` (exclu du dépôt), autorisé avec le scope `spreadsheets`. Il réutilise le même client OAuth que Gmail (`credentials.json`) mais garde un fichier de token séparé puisque les scopes diffèrent. Le premier run réel ouvre un navigateur pour l'écran de consentement une seule fois ; ensuite, `auth.get_credentials()` rafraîchit le token silencieusement, comme il le fait déjà pour Gmail.

**Étiquetage Gmail :** `gmail_labeling.py` nécessite encore un autre token, `token_gmail_modify.json` (exclu du dépôt), avec le scope plus large `gmail.modify`. Même flux de consentement one-time que ci-dessus.

## Autostart (vérification déclenchée au login)

`login_pipeline_check.py` est une couche de confort optionnelle au-dessus de `run_pipeline.py` : il propose de lancer le pipeline une fois par jour calendaire, pensé pour être déclenché automatiquement au login graphique plutôt que lancé à la main. Voir la section [`login_pipeline_check.py`](../README.fr.md#login_pipeline_checkpy) du README pour son fonctionnement détaillé.

**Configuration locale one-time** (non gérée par ce dépôt) : créer une entrée XDG autostart pour qu'un login graphique déclenche la vérification.

```
# ~/.config/autostart/jobflow-pipeline-check.desktop
[Desktop Entry]
Type=Application
Name=JobFlow pipeline check
Comment=Propose de lancer le pipeline JobFlow (une fois par jour maximum)
Exec=/usr/bin/python3 /chemin/vers/JobFlow/login_pipeline_check.py
X-GNOME-Autostart-enabled=true
NoDisplay=true
Hidden=false
```

## Se remettre d'un échec de synchronisation

`sheets_sync.py` enregistre tout échec dans `logs/sheets_sync_error.json` et refuse de tourner à nouveau (ainsi que `run_pipeline.py`) tant que ce n'est pas acquitté :

```bash
python3 sheets_sync.py --ack-error
```

Comme `sheets_sync.py` ne regarde jamais que le CSV d'import du **jour même**, un échec non acquitté un jour donné, suivi d'un run normal un jour plus tard, isole silencieusement les lignes de ce jour-là : elles ne sont jamais resynchronisées, et rien en aval ne remarque le trou de lui-même. Après avoir acquitté l'erreur, vérifier si des lignes ont été laissées de côté et les rattraper :

```bash
python3 sheets_sync_recovery.py --dry-run   # rapport seul, aucune écriture
python3 sheets_sync_recovery.py             # rattrape ce qui est trouvé
```

Ce script compare chaque ID d'offre de la feuille avec l'archive locale `output/offres.csv` et rattrape tout ce qui manque, que ce soit un trou interne ou un retard en fin de séquence. Voir la section [`sheets_sync_recovery.py`](../README.fr.md#sheets_sync_recoverypy) du README pour le comportement complet (lignes séparatrices, relances idempotentes, ce que le script refuse de toucher).
