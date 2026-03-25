from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    app_env: str
    log_level: str
    cache_ttl_seconds: int
    bexio_client_id: str
    bexio_client_secret: str
    bexio_redirect_uri: str
    bexio_auth_base_url: str
    bexio_oauth_scope: str
    bexio_api_base_url: str
    bexio_accounting_api_base_url: str
    openrouter_api_key: str
    openrouter_model: str
    openrouter_base_url: str
    ollama_base_url: str


def _get_streamlit_secret(key: str) -> str | None:
    try:
        import streamlit as st

        value = st.secrets.get(key)
        return str(value) if value is not None else None
    except Exception:
        return None


def _read_value(key: str, default: str = "") -> str:
    env_value = os.getenv(key)
    if env_value:
        return env_value
    secret_value = _get_streamlit_secret(key)
    if secret_value:
        return secret_value
    return default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        app_env=_read_value("APP_ENV", "development"),
        log_level=_read_value("LOG_LEVEL", "INFO"),
        cache_ttl_seconds=int(_read_value("REPORTIO_CACHE_TTL_SECONDS", "300")),
        bexio_client_id=_read_value("BEXIO_CLIENT_ID"),
        bexio_client_secret=_read_value("BEXIO_CLIENT_SECRET"),
        bexio_redirect_uri=_read_value("BEXIO_REDIRECT_URI", "http://localhost:8501"),
        bexio_auth_base_url=_read_value("BEXIO_AUTH_BASE_URL", "https://auth.bexio.com/realms/bexio"),
        bexio_oauth_scope=_read_value(
            "BEXIO_OAUTH_SCOPE",
            "kb_invoice_show kb_order_show offline_access",
        ),
        bexio_api_base_url=_read_value("BEXIO_API_BASE_URL", "https://api.bexio.com/2.0"),
        bexio_accounting_api_base_url=_read_value(
            "BEXIO_ACCOUNTING_API_BASE_URL",
            "https://api.bexio.com/3.0",
        ),
        openrouter_api_key=_read_value("OPENROUTER_API_KEY"),
        openrouter_model=_read_value("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        openrouter_base_url=_read_value("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        ollama_base_url=_read_value("OLLAMA_BASE_URL", "http://localhost:11434"),
    )
