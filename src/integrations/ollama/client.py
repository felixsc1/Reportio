from __future__ import annotations

from typing import Any

import httpx


def _normalize_base_url(base_url: str) -> str:
    base_url = (base_url or "").strip()
    if not base_url:
        return "http://localhost:11434"
    return base_url.rstrip("/")


def list_local_ollama_models(base_url: str) -> list[str]:
    """
    Return a list of locally available Ollama model names.

    Uses Ollama's HTTP API endpoint: GET /api/tags
    """
    url = f"{_normalize_base_url(base_url)}/api/tags"
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data: Any = resp.json()
    except Exception:
        return []

    models = data.get("models", []) if isinstance(data, dict) else []
    names: list[str] = []
    if isinstance(models, list):
        for m in models:
            if isinstance(m, dict):
                name = m.get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
    return names

