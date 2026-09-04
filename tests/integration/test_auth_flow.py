"""Flujo de autenticación completo (ADR-008)."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from softree_audit.models import RefreshToken, User
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import TEST_EMAIL, TEST_PASSWORD

pytestmark = pytest.mark.integration

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"

COOKIE = "softree_refresh"


async def _login(client: AsyncClient) -> str:
    response = await client.post(LOGIN, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


async def test_login_returns_access_token_and_user(client: AsyncClient, user: User) -> None:
    response = await client.post(LOGIN, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert response.status_code == 200

    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["user"]["email"] == TEST_EMAIL
    # El hash de la contraseña nunca debe salir de la API.
    assert "password_hash" not in response.text


async def test_login_sets_httponly_refresh_cookie(client: AsyncClient, user: User) -> None:
    response = await client.post(LOGIN, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    header = response.headers["set-cookie"]
    assert COOKIE in header
    assert "HttpOnly" in header
    assert "Path=/api/v1/auth" in header
    assert "SameSite=strict" in header.replace("SameSite=Strict", "SameSite=strict")


async def test_email_is_case_insensitive(client: AsyncClient, user: User) -> None:
    response = await client.post(
        LOGIN, json={"email": TEST_EMAIL.upper(), "password": TEST_PASSWORD}
    )
    assert response.status_code == 200


async def test_login_rejects_wrong_password(client: AsyncClient, user: User) -> None:
    response = await client.post(LOGIN, json={"email": TEST_EMAIL, "password": "incorrecta-xx"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.security
async def test_unknown_email_is_indistinguishable_from_wrong_password(
    client: AsyncClient, user: User
) -> None:
    """No debe poder deducirse si un email existe (`security.md` §4)."""
    unknown = await client.post(
        LOGIN, json={"email": "nadie@softree.test", "password": "incorrecta-xx"}
    )
    wrong = await client.post(LOGIN, json={"email": TEST_EMAIL, "password": "incorrecta-xx"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


async def test_inactive_user_cannot_log_in(
    client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    user.is_active = False
    await session.commit()

    response = await client.post(LOGIN, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "inactive_user"


async def test_me_requires_a_token(client: AsyncClient, user: User) -> None:
    response = await client.get(ME)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_me_returns_the_authenticated_user(client: AsyncClient, user: User) -> None:
    token = await _login(client)
    response = await client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == TEST_EMAIL


async def test_me_rejects_an_invalid_token(client: AsyncClient, user: User) -> None:
    response = await client.get(ME, headers={"Authorization": "Bearer no-es-un-token"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


@pytest.mark.security
async def test_refresh_token_is_not_accepted_as_access_token(
    client: AsyncClient, user: User
) -> None:
    await _login(client)
    refresh_token = client.cookies[COOKIE]
    response = await client.get(ME, headers={"Authorization": f"Bearer {refresh_token}"})
    assert response.status_code == 401


async def test_refresh_rotates_the_session(
    client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    first_access = await _login(client)
    first_refresh = client.cookies[COOKIE]

    response = await client.post(REFRESH)
    assert response.status_code == 200
    second_access = response.json()["access_token"]
    assert second_access != first_access
    assert client.cookies[COOKIE] != first_refresh

    # El token anterior queda revocado y encadenado al nuevo.
    result = await session.execute(
        sa.select(RefreshToken).where(RefreshToken.revoked_at.is_not(None))
    )
    revoked = result.scalars().all()
    assert len(revoked) == 1
    assert revoked[0].replaced_by_id is not None


async def test_refresh_without_cookie_is_rejected(client: AsyncClient, user: User) -> None:
    response = await client.post(REFRESH)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


@pytest.mark.security
async def test_reusing_a_rotated_refresh_token_revokes_the_whole_session(
    client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """Detección de reuso: indica que el token quedó expuesto (ADR-008).

    Un reuso real llega mucho después de la rotación, cuando el cliente legítimo
    ya siguió renovando. La repetición inmediata tiene su propia prueba: es una
    carrera benigna entre pestañas, no un robo.
    """
    import datetime as dt

    from softree_audit.auth.service import REFRESH_REPLAY_GRACE

    _, session = app_context
    await _login(client)
    stolen = client.cookies[COOKIE]

    assert (await client.post(REFRESH)).status_code == 200

    # Se envejece la rotación más allá de la ventana de gracia.
    await session.execute(
        sa.update(RefreshToken)
        .where(RefreshToken.revoked_at.is_not(None))
        .values(revoked_at=dt.datetime.now(dt.UTC) - REFRESH_REPLAY_GRACE - dt.timedelta(seconds=5))
    )
    await session.commit()

    # Se envía el token robado como única cookie: manipular el almacén sin
    # limpiarlo dejaría también la cookie rotada y el servidor recibiría dos.
    client.cookies.clear()
    client.cookies.set(COOKIE, stolen)
    replay = await client.post(REFRESH)
    assert replay.status_code == 401

    result = await session.execute(
        sa.select(sa.func.count())
        .select_from(RefreshToken)
        .where(RefreshToken.revoked_at.is_(None))
    )
    assert result.scalar_one() == 0


async def test_logout_revokes_the_refresh_token(client: AsyncClient, user: User) -> None:
    await _login(client)
    assert (await client.post(LOGOUT)).status_code == 204

    # La cookie fue borrada, por lo que refrescar ya no es posible.
    response = await client.post(REFRESH)
    assert response.status_code == 401


async def test_logout_is_idempotent(client: AsyncClient, user: User) -> None:
    assert (await client.post(LOGOUT)).status_code == 204
    assert (await client.post(LOGOUT)).status_code == 204


async def test_login_validates_the_payload(client: AsyncClient, user: User) -> None:
    response = await client.post(LOGIN, json={"email": "no-es-un-email", "password": "x"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert any(detail["field"] == "email" for detail in body["error"]["details"])


async def test_login_rejects_unexpected_fields(client: AsyncClient, user: User) -> None:
    """`extra="forbid"` evita que un cliente inyecte campos no previstos."""
    response = await client.post(
        LOGIN,
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "is_admin": True},
    )
    assert response.status_code == 422


@pytest.mark.security
async def test_a_replay_right_after_rotation_is_treated_as_benign(
    client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """Dos pestañas o una recarga presentan la misma cookie a la vez.

    Cerrar la sesión en ese caso sería hostil y no aporta seguridad: dentro de
    la ventana de gracia se emite un par nuevo.
    """
    _, session = app_context
    await _login(client)
    first = client.cookies[COOKIE]

    assert (await client.post(REFRESH)).status_code == 200

    client.cookies.clear()
    client.cookies.set(COOKIE, first)
    replay = await client.post(REFRESH)

    assert replay.status_code == 200
    assert replay.json()["access_token"]
    # La sesión sigue viva.
    assert (
        await client.get(ME, headers={"Authorization": f"Bearer {replay.json()['access_token']}"})
    ).status_code == 200

    remaining = await session.execute(
        sa.select(sa.func.count())
        .select_from(RefreshToken)
        .where(RefreshToken.revoked_at.is_(None))
    )
    assert remaining.scalar_one() == 1
