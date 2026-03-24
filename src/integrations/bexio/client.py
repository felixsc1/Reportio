from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config.settings import Settings
from src.integrations.bexio.models import BexioApiError, OAuthToken
from src.integrations.bexio.oauth import BexioOAuthManager
from src.utils.cache import TTLCache

logger = logging.getLogger(__name__)


class BexioClient:
    def __init__(self, settings: Settings, token: OAuthToken | None = None) -> None:
        self.settings = settings
        self.oauth = BexioOAuthManager(settings)
        self.token = token
        self.cache = TTLCache(settings.cache_ttl_seconds)
        self._client = httpx.Client(base_url=settings.bexio_api_base_url.rstrip("/"), timeout=30.0)

    def set_token(self, token: OAuthToken) -> None:
        self.token = token

    def _ensure_token(self) -> OAuthToken:
        if self.token is None:
            raise BexioApiError(status_code=401, message="Missing OAuth token")
        if self.token.needs_refresh and self.token.refresh_token:
            self.token = self.oauth.refresh_access_token(self.token.refresh_token)
        return self.token

    def _headers(self) -> dict[str, str]:
        token = self._ensure_token()
        return {"Authorization": f"Bearer {token.access_token}", "Accept": "application/json"}

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    )
    def _request(self, method: str, endpoint: str, json_body: Any | None = None) -> list[dict[str, Any]]:
        response = self._client.request(method, endpoint, headers=self._headers(), json=json_body)
        if response.status_code in (429, 500, 502, 503, 504):
            raise httpx.NetworkError(f"Transient Bexio API error: {response.status_code}")
        if response.status_code >= 400:
            raise BexioApiError(status_code=response.status_code, message=response.text[:500])
        data = response.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def _cached_post(self, endpoint: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        cache_key = f"{endpoint}:{json.dumps(payload, sort_keys=True)}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached

        rows = self._request("POST", endpoint, json_body=payload)
        self.cache.set(cache_key, rows)
        return rows

    def _paginated_post(self, endpoint: str, base_payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        payload = dict(base_payload or {})
        payload.setdefault("limit", 200)
        payload.setdefault("offset", 0)

        all_rows: list[dict[str, Any]] = []
        while True:
            page_rows = self._cached_post(endpoint, payload)
            all_rows.extend(page_rows)
            if len(page_rows) < payload["limit"]:
                break
            payload["offset"] += payload["limit"]
        return all_rows

    def list_invoices(self, include_open: bool = True, include_paid: bool = True) -> list[dict[str, Any]]:
        rows = self._paginated_post("/kb_invoice/search", {})
        if include_open and include_paid:
            return rows
        wanted = set()
        if include_open:
            wanted.add("open")
        if include_paid:
            wanted.add("paid")
        return [row for row in rows if str(row.get("status", "")).lower() in wanted]

    def list_orders_or_quotes(self) -> list[dict[str, Any]]:
        return self._paginated_post("/kb_order/search", {})

    def list_journal_entries(self) -> list[dict[str, Any]]:
        return self._paginated_post("/journal/search", {})

    def list_accounts(self) -> list[dict[str, Any]]:
        return self._paginated_post("/account/search", {})

    def search(self, endpoint: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        return self._paginated_post(endpoint, filters)

    def close(self) -> None:
        self._client.close()
