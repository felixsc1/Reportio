from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx

from src.config.settings import Settings
from src.integrations.bexio.models import OAuthToken


class BexioOAuthManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def authorize_url(self) -> str:
        return f"{self.settings.bexio_auth_base_url.rstrip('/')}/oauth/authorize"

    @property
    def token_url(self) -> str:
        return f"{self.settings.bexio_auth_base_url.rstrip('/')}/oauth/token"

    def build_authorization_url(self, state: str, scope: str = "offline_access") -> str:
        params = {
            "response_type": "code",
            "client_id": self.settings.bexio_client_id,
            "redirect_uri": self.settings.bexio_redirect_uri,
            "scope": scope,
            "state": state,
        }
        return f"{self.authorize_url}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> OAuthToken:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.bexio_redirect_uri,
            "client_id": self.settings.bexio_client_id,
            "client_secret": self.settings.bexio_client_secret,
        }
        with httpx.Client(timeout=20.0) as client:
            response = client.post(self.token_url, data=data)
            response.raise_for_status()
            payload = response.json()
        return OAuthToken.from_payload(payload)

    def refresh_access_token(self, refresh_token: str) -> OAuthToken:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.settings.bexio_client_id,
            "client_secret": self.settings.bexio_client_secret,
        }
        with httpx.Client(timeout=20.0) as client:
            response = client.post(self.token_url, data=data)
            response.raise_for_status()
            payload = response.json()
        return OAuthToken.from_payload(payload)
