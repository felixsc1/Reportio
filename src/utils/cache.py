from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheItem:
    value: Any
    expires_at: float


class TTLCache:
    def __init__(self, ttl_seconds: int) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, CacheItem] = {}

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        if item.expires_at < time.time():
            self._store.pop(key, None)
            return None
        return item.value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = CacheItem(value=value, expires_at=time.time() + self.ttl_seconds)

    def clear(self) -> None:
        self._store.clear()
