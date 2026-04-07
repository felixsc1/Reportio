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
        self._accounting_client = httpx.Client(
            base_url=settings.bexio_accounting_api_base_url.rstrip("/"),
            timeout=30.0,
        )

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
    def _request(
        self,
        method: str,
        endpoint: str,
        json_body: Any | None = None,
        params: dict[str, Any] | None = None,
        *,
        use_accounting_api: bool = False,
    ) -> list[dict[str, Any]]:
        headers = self._headers()
        client = self._accounting_client if use_accounting_api else self._client
        logger.info(
            "Bexio API request: %s %s | Content-Type=%s | params=%s | body_type=%s | body=%s",
            method, 
            endpoint, 
            headers.get("Content-Type"), 
            params,
            type(json_body).__name__,
            json_body if json_body is None or len(str(json_body)) < 100 else "[...]"
        )

        response = client.request(
            method, 
            endpoint, 
            headers=headers, 
            json=json_body,
            params=params,
        )

        logger.info("Bexio API response: %s %s -> %s", method, endpoint, response.status_code)

        if response.status_code in (429, 500, 502, 503, 504):
            raise httpx.NetworkError(f"Transient Bexio API error: {response.status_code}")

        if response.status_code >= 400:
            error_body = response.text[:800]
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

    def _try_paginated_post(self, endpoints: list[str], base_payload: dict[str, Any] | list | None = None) -> list[dict[str, Any]]:
        last_exc: Exception | None = None
        for endpoint in endpoints:
            try:
                return self._paginated_post(endpoint, base_payload=base_payload)
            except BexioApiError as exc:
                last_exc = exc
                if exc.status_code == 404:
                    continue
                raise
        if last_exc:
            raise last_exc
        return []

    def _try_cached_get(self, endpoints: list[str], *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        last_exc: Exception | None = None
        for endpoint in endpoints:
            try:
                return self._cached_get(endpoint, params=params, use_accounting_api=False)
            except BexioApiError as exc:
                last_exc = exc
                if exc.status_code == 404:
                    continue
                raise
        if last_exc:
            raise last_exc
        return []

    def _cached_get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        use_accounting_api: bool = False,
    ) -> list[dict[str, Any]]:
        cache_key = f"GET:{'v3' if use_accounting_api else 'v2'}:{endpoint}:{json.dumps(params or {}, sort_keys=True)}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug("Cache hit for %s", cache_key)
            return cached

        rows = self._request("GET", endpoint, json_body=None, params=params, use_accounting_api=use_accounting_api)
        self.cache.set(cache_key, rows)
        return rows

    def _paginated_post(self, endpoint: str, base_payload: dict[str, Any] | list | None = None) -> list[dict[str, Any]]:
        # Bexio search expects a JSON array of filter objects.
        # Empty list `[]` should return all records. If it fails, we try a minimal filter.
        if isinstance(base_payload, dict) or base_payload is None:
            payload: list = []
        else:
            payload = list(base_payload) if base_payload is not None else []

        # Fallback: if empty list fails, try a filter that matches everything
        if not payload:
            payload = [{"field": "id", "value": "", "criteria": ">="}]

        all_rows: list[dict[str, Any]] = []
        limit = 200
        offset = 0
        while True:
            page_payload = payload.copy() if isinstance(payload, list) else []
            page_rows = self._cached_post(endpoint, page_payload)
            all_rows.extend(page_rows)
            if len(page_rows) < limit:
                break
            offset += limit
        return all_rows

    def _paginated_get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        limit_param: str = "limit",
        offset_param: str = "offset",
        page_size: int = 2000,
        use_accounting_api: bool = False,
    ) -> list[dict[str, Any]]:
        all_rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            page_params = dict(params or {})
            page_params[limit_param] = page_size
            page_params[offset_param] = offset
            page_rows = self._cached_get(endpoint, page_params, use_accounting_api=use_accounting_api)
            all_rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
            offset += page_size
        return all_rows

    def _paginated_get_by_page(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        page_param: str = "page",
        limit_param: str = "limit",
        page_size: int = 500,
        use_accounting_api: bool = False,
    ) -> list[dict[str, Any]]:
        all_rows: list[dict[str, Any]] = []
        page = 1
        while True:
            page_params = dict(params or {})
            page_params[limit_param] = page_size
            page_params[page_param] = page
            page_rows = self._cached_get(endpoint, page_params, use_accounting_api=use_accounting_api)
            if not page_rows:
                break
            all_rows.extend(page_rows)
            if len(page_rows) < page_size:
                break
            page += 1
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

    def list_bills(self) -> list[dict[str, Any]]:
        # Supplier bills are not consistently exposed under the same resource path across
        # API variants/accounts. Try known/observed purchase endpoints and fall back to
        # purchase expenses (which many accounts have enabled).
        return self._try_paginated_post(
            [
                "/kb_bill/search",
                "/purchase/bill/search",
                "/purchase/bills/search",
                "/kb_expense/search",
            ]
        )

    def list_orders_or_quotes(self) -> list[dict[str, Any]]:
        return self._paginated_post("/kb_order/search")

    def list_journal_entries(self) -> list[dict[str, Any]]:
        return self._paginated_post("/journal/search")

    def list_accounts(self) -> list[dict[str, Any]]:
        return self._paginated_post("/account/search")

    def list_accounting_journal(
        self,
        *,
        from_date: str | None = None,
        to_date: str | None = None,
        account_uuid: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if account_uuid:
            params["account_uuid"] = account_uuid
        return self._paginated_get(
            "/accounting/journal",
            params=params,
            page_size=2000,
            use_accounting_api=True,
        )

    def list_accounts_v2(self) -> list[dict[str, Any]]:
        # v2 endpoint (2.0) returns numeric ids + account_no + name which we can use for P&L mapping.
        return self._paginated_get("/accounts", page_size=2000, use_accounting_api=False)

    def list_invoices_v2(self, *, page_size: int = 500, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        # Backwards compatible name: prefer search endpoint used elsewhere in the app.
        del page_size, params
        return self.list_invoices(include_open=True, include_paid=True)

    def list_bills_v2(self, *, page_size: int = 500, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        # Backwards compatible name: supplier bills are accessed via search endpoint.
        del page_size, params
        return self.list_bills()

    def list_invoice_payments(self, invoice_id: int | str) -> list[dict[str, Any]]:
        return self._cached_get(f"/kb_invoice/{invoice_id}/payment", use_accounting_api=False)

    def list_bill_payments(self, bill_id: int | str) -> list[dict[str, Any]]:
        return self._try_cached_get(
            [
                f"/kb_bill/{bill_id}/payment",
                f"/purchase/bill/{bill_id}/payment",
                f"/purchase/bills/{bill_id}/payment",
                f"/kb_expense/{bill_id}/payment",
            ]
        )

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
        self._accounting_client.close()
