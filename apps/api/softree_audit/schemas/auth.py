"""Esquemas de autenticación."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from pydantic import EmailStr, Field, field_validator

from softree_audit.schemas.common import ApiModel

# Longitud mínima razonable para una herramienta interna; la máxima existe
# porque Argon2 hashea la contraseña completa y una entrada enorme sería un
# vector de consumo de CPU.
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 256

# Longitud máxima de una dirección de correo según RFC 5321.
EMAIL_MAX_LENGTH = 320


def normalize_email_form(value: str) -> str:
    """Normaliza y comprueba solo la forma del email, no su existencia."""
    normalized = value.strip().lower()
    local, separator, domain = normalized.partition("@")
    if not separator or not local or not domain or "@" in domain:
        raise ValueError("El email debe tener la forma usuario@dominio")
    return normalized


class LoginRequest(ApiModel):
    """Credenciales de acceso.

    El email se valida solo en su forma, no con `EmailStr`. La validación
    estricta rechaza dominios de uso reservado (`.test`, `.local`, `.internal`),
    que son legítimos en una herramienta interna, y rechazar un intento de login
    por el formato del email no aporta ninguna protección: la comprobación real
    es la búsqueda del usuario. La validación estricta sí se aplica al crear la
    cuenta, en `UserCreate`.
    """

    email: Annotated[str, Field(min_length=3, max_length=EMAIL_MAX_LENGTH)]
    password: Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)]

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email_form(value)


class UserRead(ApiModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    last_login_at: dt.datetime | None
    created_at: dt.datetime


class TokenResponse(ApiModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - esquema de autorización, no un secreto
    expires_in: int = Field(description="Segundos de validez del access token.")
    user: UserRead | None = None


class UserCreate(ApiModel):
    """Solo se usa desde la CLI. No hay endpoint público de registro."""

    email: EmailStr
    full_name: Annotated[str, Field(min_length=1, max_length=200)]
    password: Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class PasswordReset(ApiModel):
    """Cambio de contraseña desde la CLI, para un usuario que ya existe.

    El email se valida como en `LoginRequest`, no como en `UserCreate`: la
    cuenta ya existe, y una dirección con un dominio de uso reservado
    (`.test`, `.local`, `.internal`) es legítima en una herramienta interna.
    Aplicar aquí la validación estricta dejaría a esas cuentas sin manera de
    recuperar el acceso.
    """

    email: Annotated[str, Field(min_length=3, max_length=EMAIL_MAX_LENGTH)]
    password: Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email_form(value)
