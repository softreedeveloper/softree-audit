"""Emisión y validación de tokens JWT (ADR-008)."""

from __future__ import annotations

import datetime as dt
import uuid

import jwt
import pytest
from softree_audit.core.errors import InvalidTokenError
from softree_audit.core.security import ALGORITHM, create_token, decode_token
from uuid6 import uuid7

pytestmark = pytest.mark.unit

SECRET = "clave-de-prueba-suficientemente-larga-0123456789"
OTHER_SECRET = "otra-clave-de-prueba-suficientemente-larga-9876"


def _issue(
    token_type: str = "access",  # noqa: S107 - tipo de token, no una credencial
    ttl: dt.timedelta | None = None,
) -> tuple[uuid.UUID, str]:
    subject = uuid7()
    issued = create_token(
        subject=subject,
        token_type=token_type,  # type: ignore[arg-type]
        secret_key=SECRET,
        ttl=ttl or dt.timedelta(minutes=15),
    )
    return subject, issued.token


def test_round_trip_preserves_subject() -> None:
    subject, token = _issue()
    claims = decode_token(token, secret_key=SECRET, expected_type="access")
    assert claims.subject == subject
    assert claims.token_type == "access"


def test_each_token_has_a_unique_jti() -> None:
    _, first = _issue()
    _, second = _issue()
    a = decode_token(first, secret_key=SECRET, expected_type="access")
    b = decode_token(second, secret_key=SECRET, expected_type="access")
    assert a.token_id != b.token_id


def test_access_token_is_rejected_where_refresh_is_expected() -> None:
    """Separar los tipos evita que un access token sirva para refrescar."""
    _, token = _issue("access")
    with pytest.raises(InvalidTokenError):
        decode_token(token, secret_key=SECRET, expected_type="refresh")


def test_refresh_token_is_rejected_where_access_is_expected() -> None:
    _, token = _issue("refresh")
    with pytest.raises(InvalidTokenError):
        decode_token(token, secret_key=SECRET, expected_type="access")


def test_token_signed_with_another_key_is_rejected() -> None:
    _, token = _issue()
    with pytest.raises(InvalidTokenError):
        decode_token(token, secret_key=OTHER_SECRET, expected_type="access")


def test_expired_token_is_rejected() -> None:
    _, token = _issue(ttl=dt.timedelta(seconds=-10))
    with pytest.raises(InvalidTokenError):
        decode_token(token, secret_key=SECRET, expected_type="access")


def test_tampered_token_is_rejected() -> None:
    _, token = _issue()
    header, payload, signature = token.split(".")
    with pytest.raises(InvalidTokenError):
        decode_token(f"{header}.{payload}x.{signature}", secret_key=SECRET, expected_type="access")


def test_garbage_is_rejected() -> None:
    with pytest.raises(InvalidTokenError):
        decode_token("no-es-un-jwt", secret_key=SECRET, expected_type="access")


@pytest.mark.security
def test_unsigned_token_is_rejected() -> None:
    """El algoritmo `none` no debe aceptarse en ninguna circunstancia."""
    forged = jwt.encode(
        {
            "sub": str(uuid7()),
            "jti": str(uuid7()),
            "typ": "access",
            "iat": int(dt.datetime.now(dt.UTC).timestamp()),
            "exp": int((dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)).timestamp()),
            "iss": "softree-audit",
        },
        key="",
        algorithm="none",
    )
    with pytest.raises(InvalidTokenError):
        decode_token(forged, secret_key=SECRET, expected_type="access")


@pytest.mark.security
def test_token_from_another_issuer_is_rejected() -> None:
    forged = jwt.encode(
        {
            "sub": str(uuid7()),
            "jti": str(uuid7()),
            "typ": "access",
            "iat": int(dt.datetime.now(dt.UTC).timestamp()),
            "exp": int((dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)).timestamp()),
            "iss": "otro-emisor",
        },
        SECRET,
        algorithm=ALGORITHM,
    )
    with pytest.raises(InvalidTokenError):
        decode_token(forged, secret_key=SECRET, expected_type="access")


@pytest.mark.security
def test_token_without_required_claims_is_rejected() -> None:
    forged = jwt.encode({"sub": str(uuid7()), "iss": "softree-audit"}, SECRET, algorithm=ALGORITHM)
    with pytest.raises(InvalidTokenError):
        decode_token(forged, secret_key=SECRET, expected_type="access")
