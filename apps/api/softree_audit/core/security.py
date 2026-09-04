"""Primitivas de autenticación: hash de contraseñas y tokens JWT.

Decisiones en ADR-008 y `docs/spec/security.md` §4.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from uuid6 import uuid7

from softree_audit.core.errors import InvalidTokenError

TokenType = Literal["access", "refresh"]

ALGORITHM = "HS256"

# Parámetros de Argon2id documentados en security.md §4.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

# Hash señuelo para igualar el tiempo de respuesta cuando el email no existe,
# evitando enumeración de usuarios (security.md §4).
_DECOY_HASH = _hasher.hash("softree-audit-decoy-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def waste_time_like_verification() -> None:
    """Consume un tiempo equivalente a una verificación real.

    Se invoca cuando el email no existe para que el atacante no pueda
    distinguir «usuario inexistente» de «contraseña incorrecta» por latencia.
    """
    verify_password("softree-audit-decoy-password-wrong", _DECOY_HASH)


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Claims validados de un token emitido por esta aplicación."""

    subject: uuid.UUID
    token_id: uuid.UUID
    token_type: TokenType
    issued_at: dt.datetime
    expires_at: dt.datetime


@dataclass(frozen=True, slots=True)
class IssuedToken:
    token: str
    token_id: uuid.UUID
    expires_at: dt.datetime


def create_token(
    *,
    subject: uuid.UUID,
    token_type: TokenType,
    secret_key: str,
    ttl: dt.timedelta,
    token_id: uuid.UUID | None = None,
) -> IssuedToken:
    now = utcnow()
    jti = token_id or uuid7()
    expires_at = now + ttl
    payload: dict[str, Any] = {
        "sub": str(subject),
        "jti": str(jti),
        "typ": token_type,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": "softree-audit",
    }
    token = jwt.encode(payload, secret_key, algorithm=ALGORITHM)
    return IssuedToken(token=token, token_id=jti, expires_at=expires_at)


def decode_token(token: str, *, secret_key: str, expected_type: TokenType) -> TokenClaims:
    """Decodifica y valida un token. Lanza `InvalidTokenError` si no es válido."""
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[ALGORITHM],
            issuer="softree-audit",
            options={"require": ["sub", "jti", "typ", "exp", "iat"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc

    if payload.get("typ") != expected_type:
        # Un access token no debe servir para refrescar ni al contrario.
        raise InvalidTokenError()

    try:
        subject = uuid.UUID(str(payload["sub"]))
        token_id = uuid.UUID(str(payload["jti"]))
    except (ValueError, KeyError) as exc:
        raise InvalidTokenError() from exc

    return TokenClaims(
        subject=subject,
        token_id=token_id,
        token_type=expected_type,
        issued_at=dt.datetime.fromtimestamp(payload["iat"], tz=dt.UTC),
        expires_at=dt.datetime.fromtimestamp(payload["exp"], tz=dt.UTC),
    )
