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
        return {
            "Authorization": f"Bearer {token.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    )
    def _request(self, method: str, endpoint: str, json_body: Any | None = None) -> list[dict[str, Any]]:
        logger.debug("Bexio API request: %s %s with body=%s", method, endpoint, json_body)
        response = self._client.request(method, endpoint, headers=self._headers(), json=json_body)

        if response.status_code in (429, 500, 502, 503, 504):
            raise httpx.NetworkError(f"Transient Bexio API error: {response.status_code}")

        if response.status_code >= 400:
            error_body = response.text[:500]
            logger.error("Bexio API error %s %s: %s", response.status_code, endpoint, error_body)
            raise BexioApiError(status_code=response.status_code, message=error_body)

        try:
            data = response.json()
        except Exception as exc:
            logger.error("Failed to parse JSON from Bexio response: %s", exc)
            raise BexioApiError(status_code=response.status_code, message="Invalid JSON response") from exc

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def _cached_post(self, endpoint: str, payload: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
        cache_key = f"{endpoint}:{json.dumps(payload, sort_keys=True)}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for %s", cache_key)
            return cached

        rows = self._request("POST", endpoint, json_body=payload)
        self.cache.set(cache_key, rows)
        return rows

    def _paginated_post(self, endpoint: str, base_payload: dict[str, Any] | list | None = None) -> list[dict[str, Any]]:
        # For Bexio search endpoints, the payload must be a list of search criteria objects (even if empty).
        # Passing {} or dict causes 400 "field not set" error.
        if isinstance(base_payload, dict) or base_payload is None:
            payload: list[dict[str, Any]] = []
        else:
            payload = list(base_payload) if base_payload else []

        all_rows: list[dict[str, Any]] = []
        limit = 200
        offset = 0
        while True:
            page_payload = payload.copy() if isinstance(payload, list) else []
            # Bexio supports limit/offset as query params for search, but for simplicity we use empty criteria list
            page_rows = self._cached_post(endpoint, page_payload)
            all_rows.extend(page_rows)
            if len(page_rows) < limit:
                break
            offset += limit
        return all_rows

    def list_invoices(self, include_open: bool = True, include_paid: bool = True) -> list[dict[str, Any]]:
        rows = self._paginated_post("/kb_invoice/search")
        if include_open and include_paid:
            return rows
        wanted = set()
        if include_open:
            wanted.add("open")
        if include_paid:
            wanted.add("paid")
        return [row for row in rows if str(row.get("status", "")).lower() in wanted]

    def list_orders_or_quotes(self) -> list[dict[str, Any]]:
        return self._paginated_post("/kb_order/search")

    def list_journal_entries(self) -> list[dict[str, Any]]:
        return self._paginated_post("/journal/search")

    def list_accounts(self) -> list[dict[str, Any]]:
        return self._paginated_post("/account/search")

    def search(self, endpoint: str, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        # Pass empty list for search criteria (Bexio expects array of filter objects)
        search_payload: list = [] if filters is None else []
        return self._paginated_post(endpoint, search_payload)

    def clear_cache(self) -> None:
        """Clear the TTL cache. Useful after fixing auth/search issues."""
        self.cache.clear()
        logger.info("BexioClient cache cleared")

    def close(self) -> None:
        self._client.close()
