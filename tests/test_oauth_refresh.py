from __future__ import annotations

from datetime import datetime, timedelta

from src.integrations.bexio.models import OAuthToken


def test_token_needs_refresh_when_expiring_soon():
    token = OAuthToken(
        access_token="a",
        refresh_token="r",
        expires_at=datetime.utcnow() + timedelta(seconds=30),
    )
    assert token.needs_refresh is True
