from __future__ import annotations

import logging
from urllib.parse import urlencode

import httpx

from src.config.settings import Settings
from src.integrations.bexio.models import OAuthToken

logger = logging.getLogger(__name__)


class BexioOAuthManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._authorization_endpoint: str | None = None
        self._token_endpoint: str | None = None

    def _normalize_issuer(self) -> str:
        base = self.settings.bexio_auth_base_url.rstrip("/")
        if base.endswith("/realms/bexio"):
            return base
        if base == "https://auth.bexio.com":
            # New IdP issuer root according to bexio docs.
            return "https://auth.bexio.com/realms/bexio"
        return base

    def _discover_oidc_endpoints(self) -> tuple[str, str] | None:
        issuer = self._normalize_issuer()
        url = f"{issuer}/.well-known/openid-configuration"
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()
            auth_endpoint = str(payload.get("authorization_endpoint", "")).strip()
            token_endpoint = str(payload.get("token_endpoint", "")).strip()
            if auth_endpoint and token_endpoint:
                return auth_endpoint, token_endpoint
        except Exception as exc:
            logger.warning("Failed OAuth discovery, using fallback endpoints: %s", exc)
        return None

    def _fallback_endpoints(self) -> tuple[str, str]:
        issuer = self._normalize_issuer()
        if "idp.bexio.com" in issuer:
            return "https://idp.bexio.com/authorize", "https://idp.bexio.com/token"
        if issuer.endswith("/realms/bexio"):
            return (
                f"{issuer}/protocol/openid-connect/auth",
                f"{issuer}/protocol/openid-connect/token",
            )
        # Last-resort compatibility fallback.
        base = self.settings.bexio_auth_base_url.rstrip("/")
        return f"{base}/oauth/authorize", f"{base}/oauth/token"

    def _ensure_endpoints(self) -> None:
        if self._authorization_endpoint and self._token_endpoint:
            return
        discovered = self._discover_oidc_endpoints()
        if discovered:
            self._authorization_endpoint, self._token_endpoint = discovered
            return
        self._authorization_endpoint, self._token_endpoint = self._fallback_endpoints()

    @property
    def authorize_url(self) -> str:
        self._ensure_endpoints()
        return str(self._authorization_endpoint)

    @property
    def token_url(self) -> str:
        self._ensure_endpoints()
        return str(self._token_endpoint)

    def build_authorization_url(self, state: str, scope: str | None = None) -> str:
        resolved_scope = scope or self.settings.bexio_oauth_scope
        params = {
            "response_type": "code",
            "client_id": self.settings.bexio_client_id,
            "redirect_uri": self.settings.bexio_redirect_uri,
            "state": state,
        }
        if resolved_scope.strip():
            params["scope"] = resolved_scope
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
