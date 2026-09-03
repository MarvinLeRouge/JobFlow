[🇫🇷 Version française](setup_gmail_auth.fr.md) | 🇬🇧 English version

---

# Gmail API OAuth2 setup

Walkthrough for setting up Gmail API access for `fetch_gmail.py`, written as each step was actually completed and verified.

## 1. Google Cloud project and Gmail API activation

1. Create a new project in the [Google Cloud Console](https://console.cloud.google.com) (or reuse an existing personal one).
2. Go to **APIs & Services -> Library**, search "Gmail API", click **Enable**.
3. Verify: **APIs & Services -> Enabled APIs** lists "Gmail API".

## 2. OAuth consent screen and credentials

1. **APIs & Services -> OAuth consent screen**: choose **External** (the only option available for a plain personal Gmail account). Testing mode works for personal use, but see the caveat below before relying on it long-term; add your own address as a test user if prompted.
2. **APIs & Services -> Credentials -> + CREATE CREDENTIALS -> OAuth client ID**.
3. Application type: **Desktop app**.
4. Download the resulting JSON, save it as `credentials.json` at the project root (same directory as `auth.py`).

Verified: the downloaded file parses as valid JSON and its only top-level key is `installed` (confirms a Desktop app client, matching what `InstalledAppFlow.from_client_secrets_file()` expects). `git check-ignore credentials.json` confirms it is excluded from version control.

## 3. First authorization and refresh verification

With `auth.py` and `credentials.json` in place:

```bash
python3 -c "from auth import get_credentials; get_credentials(); print('OK')"
```

This prints an authorization URL and opens it in a browser. Log in with the Gmail account to monitor and grant the read-only permission. On success, `token.json` is created at the project root.

**Troubleshooting: "Access blocked: <app> has not completed the Google verification process" (Error 403: access_denied).** This happens when the OAuth consent screen is in Testing mode (the default, and fine for personal use - no need to publish the app) but the Gmail account being authorized has not been added to the allowed testers. Fix: **APIs & Services -> OAuth consent screen -> Test users -> + ADD USERS**, add the account, save, then retry the authorization command.

Verify the token is actually usable:

```bash
python3 -c "
from auth import get_credentials
from googleapiclient.discovery import build
service = build('gmail', 'v1', credentials=get_credentials())
profile = service.users().getProfile(userId='me').execute()
print(profile['emailAddress'])
"
```

Expected: prints the monitored Gmail address.

Verify silent refresh (no browser should open): edit `token.json`'s `expiry` field to a past date, then re-run the command above. `get_credentials()` refreshes the token using the stored `refresh_token` and updates `expiry` in place - confirmed by checking `token.json`'s `expiry` moved forward after the re-run.

**Testing-mode caveat: refresh tokens expire after 7 days, regardless of use.** Confirmed live on 2026-08-18: `token_sheets.json` and `token_gmail_modify.json`, both issued on 2026-08-11, failed to refresh exactly 7 days later with `google.auth.exceptions.RefreshError: invalid_grant: Token has been expired or revoked` - Google's documented behavior for any OAuth app still in Testing publishing status, unrelated to how often the token was actually refreshed in between. `token.json` (Gmail read-only) happened to survive only because it had been re-issued more recently.

`auth.get_credentials()` now catches this and reruns the interactive consent flow instead of crashing, so a dead refresh token just means one more browser prompt rather than a hard failure - but it will keep recurring roughly every 7 days for any token that was last issued (or re-issued) more than a week ago. The permanent fix is **APIs & Services -> OAuth consent screen -> Publishing status -> PUBLISH APP**, which removes the 7-day cap entirely; for a personal app using sensitive (non-restricted) scopes like `gmail.modify` and `spreadsheets`, this does not require Google's verification review, though the consent screen may show an "unverified app" warning that is safe to click through for your own app.
