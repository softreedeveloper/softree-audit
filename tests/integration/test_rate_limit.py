"""Límites de tasa (`docs/spec/security.md` §5)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from softree_audit.core.rate_limit import LOGIN
from softree_audit.models import User

from tests.integration.conftest import TEST_EMAIL, TEST_PASSWORD

pytestmark = [pytest.mark.integration, pytest.mark.security]

LOGIN_PATH = "/api/v1/auth/login"


async def test_login_is_rate_limited_after_the_configured_attempts(
    client: AsyncClient, user: User
) -> None:
    for attempt in range(LOGIN.max_requests):
        response = await client.post(
            LOGIN_PATH, json={"email": TEST_EMAIL, "password": "incorrecta-xx"}
        )
        assert response.status_code == 401, f"intento {attempt + 1}"

    blocked = await client.post(LOGIN_PATH, json={"email": TEST_EMAIL, "password": "incorrecta-xx"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) > 0


async def test_correct_credentials_are_also_blocked_once_the_limit_is_reached(
    client: AsyncClient, user: User
) -> None:
    """El límite protege la cuenta, no solo los intentos fallidos."""
    for _ in range(LOGIN.max_requests):
        await client.post(LOGIN_PATH, json={"email": TEST_EMAIL, "password": "incorrecta-xx"})

    blocked = await client.post(LOGIN_PATH, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert blocked.status_code == 429


async def test_successful_login_clears_the_counter(client: AsyncClient, user: User) -> None:
    for _ in range(LOGIN.max_requests - 1):
        await client.post(LOGIN_PATH, json={"email": TEST_EMAIL, "password": "incorrecta-xx"})

    ok = await client.post(LOGIN_PATH, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert ok.status_code == 200

    # Tras un login correcto el usuario legítimo vuelve a tener margen completo.
    again = await client.post(LOGIN_PATH, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert again.status_code == 200


async def test_two_users_behind_the_same_ip_do_not_block_each_other(
    client: AsyncClient, user: User, other_user: User
) -> None:
    """El límite del refresco es por usuario, no por IP.

    Con un único cliente HTTP —misma IP para el servidor— dos sesiones distintas
    deben tener presupuestos independientes: detrás de un proxy corporativo
    todos los usuarios comparten dirección.
    """
    from softree_audit.core.rate_limit import REFRESH

    await client.post(LOGIN_PATH, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})

    # Se consume buena parte del presupuesto del primer usuario.
    for _ in range(REFRESH.max_requests // 2):
        assert (await client.post("/api/v1/auth/refresh")).status_code == 200

    # El segundo usuario, desde la misma IP, empieza con su presupuesto intacto.
    client.cookies.clear()
    second = await client.post(
        LOGIN_PATH, json={"email": "otro@softree.test", "password": TEST_PASSWORD}
    )
    assert second.status_code == 200
    assert (await client.post("/api/v1/auth/refresh")).status_code == 200


async def test_a_session_can_navigate_without_hitting_the_limit(
    client: AsyncClient, user: User
) -> None:
    """Cada carga de página renueva el token: el límite no debe estorbar."""
    from softree_audit.core.rate_limit import REFRESH

    assert REFRESH.max_requests >= 60, "un límite bajo expulsaría al usuario al navegar"

    await client.post(LOGIN_PATH, json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    for index in range(40):
        assert (await client.post("/api/v1/auth/refresh")).status_code == 200, index
