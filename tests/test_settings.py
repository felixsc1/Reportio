from __future__ import annotations

from src.config.settings import get_settings


def test_settings_load_defaults(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.openrouter_model
    assert settings.cache_ttl_seconds > 0
