🇫🇷 Version française | [🇬🇧 English version](setup_gmail_auth.md)

---

# Configuration OAuth2 de l'API Gmail

Pas-à-pas pour mettre en place l'accès à l'API Gmail pour `fetch_gmail.py`, rédigé au fil de chaque étape réellement effectuée et vérifiée.

## 1. Projet Google Cloud et activation de l'API Gmail

1. Créer un nouveau projet dans la [Google Cloud Console](https://console.cloud.google.com) (ou réutiliser un projet personnel existant).
2. Aller dans **APIs & Services -> Library**, chercher "Gmail API", cliquer sur **Enable**.
3. Vérifier : **APIs & Services -> Enabled APIs** liste "Gmail API".

## 2. Écran de consentement OAuth et identifiants

1. **APIs & Services -> OAuth consent screen** : choisir **External** (seule option disponible pour un compte Gmail personnel classique). Le mode Testing fonctionne pour un usage personnel, mais voir la mise en garde ci-dessous avant de s'y fier durablement ; ajouter sa propre adresse comme testeur si demandé.
2. **APIs & Services -> Credentials -> + CREATE CREDENTIALS -> OAuth client ID**.
3. Type d'application : **Desktop app**.
4. Télécharger le JSON obtenu, l'enregistrer sous `credentials.json` à la racine du projet (même dossier que `auth.py`).

Vérifié : le fichier téléchargé est un JSON valide dont la seule clé de premier niveau est `installed` (confirme un client de type Desktop app, conforme à ce qu'attend `InstalledAppFlow.from_client_secrets_file()`). `git check-ignore credentials.json` confirme qu'il est exclu du dépôt.

## 3. Première autorisation et vérification du rafraîchissement

Avec `auth.py` et `credentials.json` en place :

```bash
python3 -c "from auth import get_credentials; get_credentials(); print('OK')"
```

Cela affiche une URL d'autorisation et l'ouvre dans un navigateur. Se connecter avec le compte Gmail à surveiller et accorder la permission en lecture seule. En cas de succès, `token.json` est créé à la racine du projet.

**Dépannage : "Access blocked: <app> has not completed the Google verification process" (Error 403: access_denied).** Cela arrive quand l'écran de consentement OAuth est en mode Testing (le mode par défaut, adapté à un usage personnel - pas besoin de publier l'app) mais que le compte Gmail à autoriser n'a pas été ajouté aux testeurs autorisés. Correction : **APIs & Services -> OAuth consent screen -> Test users -> + ADD USERS**, ajouter le compte, sauvegarder, puis relancer la commande d'autorisation.

Vérifier que le token est réellement utilisable :

```bash
python3 -c "
from auth import get_credentials
from googleapiclient.discovery import build
service = build('gmail', 'v1', credentials=get_credentials())
profile = service.users().getProfile(userId='me').execute()
print(profile['emailAddress'])
"
```

Attendu : affiche l'adresse Gmail surveillée.

Vérifier le rafraîchissement silencieux (aucun navigateur ne devrait s'ouvrir) : modifier le champ `expiry` de `token.json` pour une date passée, puis relancer la commande ci-dessus. `get_credentials()` rafraîchit le token via le `refresh_token` stocké et met à jour `expiry` sur place - confirmé en vérifiant que `expiry` de `token.json` a avancé après la relance.

**Mise en garde du mode Testing : les refresh tokens expirent après 7 jours, quelle que soit leur utilisation.** Confirmé en réel le 2026-08-18 : `token_sheets.json` et `token_gmail_modify.json`, tous deux émis le 2026-08-11, ont échoué à se rafraîchir exactement 7 jours plus tard avec `google.auth.exceptions.RefreshError: invalid_grant: Token has been expired or revoked` - comportement documenté de Google pour toute app OAuth encore en statut de publication Testing, indépendant de la fréquence réelle de rafraîchissement du token entre-temps. `token.json` (Gmail lecture seule) a survécu uniquement parce qu'il avait été réémis plus récemment.

`auth.get_credentials()` intercepte désormais ce cas et relance le flux de consentement interactif au lieu de planter, donc un refresh token mort ne veut dire qu'une invite navigateur de plus plutôt qu'un échec dur - mais cela reviendra environ tous les 7 jours pour tout token émis (ou réémis) il y a plus d'une semaine. La correction permanente est **APIs & Services -> OAuth consent screen -> Publishing status -> PUBLISH APP**, qui supprime entièrement la limite de 7 jours ; pour une app personnelle utilisant des scopes sensibles (non restreints) comme `gmail.modify` et `spreadsheets`, cela ne nécessite pas de revue de vérification par Google, même si l'écran de consentement peut afficher un avertissement "unverified app" qu'il est sans risque d'ignorer pour sa propre app.
