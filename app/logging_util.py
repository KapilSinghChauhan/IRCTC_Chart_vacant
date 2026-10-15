from __future__ import annotations

import logging
import re
from typing import Any

SENSITIVE_KEYS = {
    "cookie",
    "cookies",
    "authorization",
    "proxy-authorization",
    "set-cookie",
    "csrf",
    "csrftoken",
    "greq",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "passwd",
    "secret",
    "session",
    "grauth",
}

_COOKIE_PAIR = re.compile(r"(?i)((?:cookie|authorization|token|secret|password)\s*[:=]\s*)([^;\s]+)")


def redact_value(key: str, value: Any) -> Any:
    if key.lower() in SENSITIVE_KEYS or any(part in key.lower() for part in ("cookie", "token", "auth", "secret", "password")):
        if value is None:
            return None
        text = str(value)
        return f"<redacted {len(text)} chars>"
    if isinstance(value, str):
        return _COOKIE_PAIR.sub(lambda m: m.group(1) + "<redacted>", value)
    return value


def redact_mapping(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    return {str(k): redact_value(str(k), v) for k, v in data.items()}


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("seat_engine")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger
