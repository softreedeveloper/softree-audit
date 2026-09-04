"""Logging estructurado.

Cada scan registra `scan_id`, `module`, `status`, `duration` y `error`
(requisito §41). Las claves sensibles se redactan siempre, en cualquier nivel
del evento.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "secret",
        "secret_key",
        "authorization",
        "cookie",
        "set-cookie",
        "api_key",
        "apikey",
        "client_secret",
    }
)

REDACTED = "[redacted]"


def _redact(value: Any) -> Any:
    """Redacta recursivamente las claves sensibles de dicts y listas."""
    if isinstance(value, dict):
        return {
            key: (REDACTED if str(key).lower() in SENSITIVE_KEYS else _redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    return value


def redact_processor(
    _logger: Any, _name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Procesador de structlog que redacta las claves sensibles del evento."""
    redacted: structlog.types.EventDict = _redact(dict(event_dict))
    return redacted


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    """Configura structlog y la librería estándar con una sola salida."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        force=True,
    )

    renderer: structlog.types.Processor
    if fmt == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
