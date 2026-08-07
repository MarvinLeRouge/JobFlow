# tests/test_auth.py
from unittest.mock import MagicMock, patch

import auth


def test_get_credentials_returns_valid_cached_token(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token.json")
    (tmp_path / "token.json").write_text("{}", encoding="utf-8")

    fake_creds = MagicMock(valid=True)
    with patch.object(auth.Credentials, "from_authorized_user_file", return_value=fake_creds):
        result = auth.get_credentials()

    assert result is fake_creds


def test_get_credentials_refreshes_expired_token(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token.json")
    (tmp_path / "token.json").write_text("{}", encoding="utf-8")

    fake_creds = MagicMock(valid=False, expired=True, refresh_token="r")
    fake_creds.to_json.return_value = '{"refreshed": true}'
    with patch.object(auth.Credentials, "from_authorized_user_file", return_value=fake_creds):
        result = auth.get_credentials()

    fake_creds.refresh.assert_called_once()
    assert result is fake_creds
    assert (tmp_path / "token.json").read_text(encoding="utf-8") == '{"refreshed": true}'


def test_get_credentials_runs_flow_when_no_token_file(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "TOKEN_FILE", tmp_path / "token.json")
    monkeypatch.setattr(auth, "CREDENTIALS_FILE", tmp_path / "credentials.json")

    fake_creds = MagicMock()
    fake_creds.to_json.return_value = '{"new": true}'
    fake_flow = MagicMock()
    fake_flow.run_local_server.return_value = fake_creds

    with patch.object(auth.InstalledAppFlow, "from_client_secrets_file", return_value=fake_flow):
        result = auth.get_credentials()

    fake_flow.run_local_server.assert_called_once_with(port=0)
    assert result is fake_creds
    assert (tmp_path / "token.json").read_text(encoding="utf-8") == '{"new": true}'
