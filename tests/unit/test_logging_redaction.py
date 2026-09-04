"""Redacción de claves sensibles en los logs (`security.md` §10)."""

from __future__ import annotations

import pytest
from softree_audit.core.logging import REDACTED, redact_processor

pytestmark = [pytest.mark.unit, pytest.mark.security]


def _redact(event: dict[str, object]) -> dict[str, object]:
    return redact_processor(None, "info", event)  # type: ignore[arg-type,return-value]


def test_top_level_secrets_are_redacted() -> None:
    result = _redact({"event": "auth.login", "password": "secreta", "email": "a@b.test"})
    assert result["password"] == REDACTED
    assert result["email"] == "a@b.test"


def test_nested_secrets_are_redacted() -> None:
    result = _redact({"event": "http", "headers": {"authorization": "Bearer abc", "accept": "*/*"}})
    headers = result["headers"]
    assert isinstance(headers, dict)
    assert headers["authorization"] == REDACTED
    assert headers["accept"] == "*/*"


def test_secrets_inside_lists_are_redacted() -> None:
    result = _redact({"event": "sync", "items": [{"refresh_token": "abc"}, {"ok": True}]})
    items = result["items"]
    assert isinstance(items, list)
    assert items[0] == {"refresh_token": REDACTED}
    assert items[1] == {"ok": True}


def test_key_matching_is_case_insensitive() -> None:
    result = _redact({"Set-Cookie": "session=abc", "API_KEY": "k"})
    assert result["Set-Cookie"] == REDACTED
    assert result["API_KEY"] == REDACTED


def test_event_body_is_preserved() -> None:
    result = _redact({"event": "scan.completed", "scan_id": "123", "duration_ms": 42})
    assert result == {"event": "scan.completed", "scan_id": "123", "duration_ms": 42}
