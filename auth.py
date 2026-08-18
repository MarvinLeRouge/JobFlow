"""OAuth2 credential management for the Gmail API.

token.json and credentials.json are never committed (see .gitignore).
"""

from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

ROOT = Path(__file__).parent
CREDENTIALS_FILE = ROOT / "credentials.json"
TOKEN_FILE = ROOT / "token.json"


def get_credentials(scopes: list[str] | None = None, token_file: Path | None = None) -> Credentials:
    """Return valid credentials for the given scopes, refreshing or running the
    interactive OAuth2 flow as needed. Writes/updates the given token file.

    Defaults to the Gmail read-only scope and TOKEN_FILE, preserving existing
    zero-argument call sites. Resolved inside the function body (not as
    parameter defaults) so callers can still monkeypatch the module-level
    SCOPES/TOKEN_FILE constants and have get_credentials() pick up the change."""
    if scopes is None:
        scopes = SCOPES
    if token_file is None:
        token_file = TOKEN_FILE

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)

    if creds and creds.valid:
        return creds

    refreshed = False
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            refreshed = True
        except RefreshError:
            # Refresh token expired/revoked server-side (e.g. Google's 7-day
            # cap for an OAuth app still in "Testing" publishing status) -
            # fall through to a fresh interactive consent instead of crashing.
            creds = None

    if not refreshed:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), scopes)
        creds = flow.run_local_server(port=0)

    token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds
