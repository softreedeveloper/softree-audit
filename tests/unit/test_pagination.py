"""Cursor de paginación."""

from __future__ import annotations

import pytest
from softree_audit.core.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)
from uuid6 import uuid7

pytestmark = pytest.mark.unit


def test_round_trip() -> None:
    identifier = uuid7()
    assert decode_cursor(encode_cursor(identifier)) == identifier


def test_cursor_is_url_safe() -> None:
    cursor = encode_cursor(uuid7())
    assert "=" not in cursor
    assert "+" not in cursor
    assert "/" not in cursor


@pytest.mark.parametrize("cursor", ["", "no-es-un-cursor", "!!!!", "YWJj"])
def test_invalid_cursor_raises_domain_error(cursor: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(cursor)


def test_limits_are_sane() -> None:
    assert 0 < DEFAULT_LIMIT <= MAX_LIMIT
