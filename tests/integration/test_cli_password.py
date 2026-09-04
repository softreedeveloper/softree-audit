"""Cambio de contraseña desde la CLI.

No hay endpoint para esto: los usuarios se administran por línea de comandos
(D-003). Lo que importa aquí es que el cambio invalide lo anterior.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from softree_audit.cli import UserNotFoundError, apply_password_reset
from softree_audit.models import User
from softree_audit.schemas.auth import PasswordReset
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import TEST_EMAIL, TEST_PASSWORD

pytestmark = pytest.mark.integration

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"

NEW_PASSWORD = "contrasena-nueva-de-prueba"


@pytest.mark.security
async def test_reset_replaces_the_password_and_revokes_open_sessions(
    client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context

    first = await client.post(LOGIN, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert first.status_code == 200

    revoked = await apply_password_reset(
        session, PasswordReset(email=TEST_EMAIL, password=NEW_PASSWORD)
    )
    assert revoked == 1

    # La sesión abierta con la contraseña anterior deja de servir.
    assert (await client.post(REFRESH)).status_code == 401

    assert (
        await client.post(LOGIN, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    ).status_code == 401
    assert (
        await client.post(LOGIN, json={"email": TEST_EMAIL, "password": NEW_PASSWORD})
    ).status_code == 200


async def test_reset_of_an_unknown_email_fails(
    app_context: tuple[object, AsyncSession], user: User
) -> None:
    _, session = app_context
    with pytest.raises(UserNotFoundError):
        await apply_password_reset(
            session, PasswordReset(email="nadie@softree.mx", password=NEW_PASSWORD)
        )


async def test_reset_rejects_a_short_password() -> None:
    """El mínimo es el mismo que al crear la cuenta."""
    with pytest.raises(ValueError):
        PasswordReset(email=TEST_EMAIL, password="corta")
