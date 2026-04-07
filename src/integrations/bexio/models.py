from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class OAuthToken:
    access_token: str
    refresh_token: str
    expires_at: datetime
    token_type: str = "Bearer"
    scope: str = ""

    @property
    def needs_refresh(self) -> bool:
        return datetime.utcnow() + timedelta(seconds=60) >= self.expires_at

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OAuthToken":
        expires_in = int(payload.get("expires_in", 3600))
        return cls(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token", ""),
            expires_at=datetime.utcnow() + timedelta(seconds=expires_in),
            token_type=payload.get("token_type", "Bearer"),
            scope=str(payload.get("scope", "")),
        )


@dataclass
class BexioApiError(Exception):
    status_code: int
    message: str

    def __str__(self) -> str:
        return f"BexioApiError(status_code={self.status_code}, message={self.message})"
