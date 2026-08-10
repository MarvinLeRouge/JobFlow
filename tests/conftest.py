from email.message import EmailMessage

import pytest


@pytest.fixture
def make_msg():
    """Build a minimal email.message.EmailMessage, the type extract_eml's
    provider extractors receive as `msg` (only the Subject header is used)."""

    def _make(subject: str = ""):
        msg = EmailMessage()
        msg["Subject"] = subject
        return msg

    return _make
