from __future__ import annotations

import logging
import re

SENSITIVE_PATTERN = re.compile(r"(authorization|access_token|refresh_token)\s*[:=]\s*([^\s,]+)", re.IGNORECASE)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        return SENSITIVE_PATTERN.sub(r"\1=[REDACTED]", message)


def configure_logging(level: str) -> None:
    logger = logging.getLogger()
    logger.setLevel(level.upper())
    logger.handlers.clear()

    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
