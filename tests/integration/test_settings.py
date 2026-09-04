"""Configuración de la instancia expuesta a la interfaz.

Lo importante aquí no es el contenido sino el límite: el endpoint dice si una
integración tiene credenciales, nunca cuáles son.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient
from softree_audit.core.config import Settings
from softree_audit.models import User

from tests.integration.conftest import TEST_PASSWORD

pytestmark = pytest.mark.integration

SETTINGS = "/api/v1/settings"


async def test_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(SETTINGS)
    assert response.status_code == 401


async def test_returns_effective_configuration(auth_client: AsyncClient, user: User) -> None:
    response = await auth_client.get(SETTINGS)
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["environment"] == "development"
    assert body["user_email"] == user.email
    assert body["user_full_name"] == user.full_name

    weights = body["scoring"]
    assert set(weights) == {"security", "performance", "seo", "accessibility", "best_practices"}
    assert sum(weights.values()) == pytest.approx(1.0)

    # El scope de un sitio nunca puede superar estos máximos.
    assert body["scope_defaults"]["max_pages"] > 0
    assert body["scope_defaults"]["max_depth"] > 0
    assert body["allowed_ports"]

    assert body["access_token_ttl_minutes"] > 0
    assert body["refresh_token_ttl_days"] > 0
    assert body["app_version"] and body["scan_engine_version"] and body["report_version"]


async def test_reports_ssrf_protection_state(auth_client: AsyncClient) -> None:
    """La interfaz debe poder avisar si se permitió el acceso a redes privadas."""
    response = await auth_client.get(SETTINGS)
    assert response.json()["ssrf_allow_private_networks"] is False


async def test_integrations_expose_state_not_values(
    auth_client: AsyncClient, settings: Settings
) -> None:
    response = await auth_client.get(SETTINGS)
    integrations = {item["key"]: item for item in response.json()["integrations"]}

    assert set(integrations) == {"zap", "pagespeed", "search_console", "ai"}
    for integration in integrations.values():
        assert isinstance(integration["configured"], bool)
        assert integration["detail"]
        # Solo los nombres de las variables, para saber qué definir.
        assert all(name.isupper() for name in integration["variables"])

    # El URI de redirección no es un secreto y hace falta para configurar Google.
    assert integrations["search_console"]["callback_url"] == settings.google_redirect_uri
    assert integrations["zap"]["callback_url"] is None

    assert integrations["pagespeed"]["configured"] is bool(settings.pagespeed_api_key)
    assert integrations["search_console"]["configured"] is bool(
        settings.google_client_id and settings.google_client_secret
    )


async def test_never_serialises_secret_values(
    auth_client: AsyncClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con todas las credenciales presentes, ninguna aparece en la respuesta."""
    secrets = {
        "ai_api_key": "ia-secreto-de-prueba",
        "zap_api_key": "zap-secreto-de-prueba",
        "pagespeed_api_key": "psi-secreto-de-prueba",
        "google_client_id": "cliente-secreto-de-prueba",
        "google_client_secret": "google-secreto-de-prueba",
    }
    for field, value in secrets.items():
        monkeypatch.setattr(settings, field, value, raising=True)

    response = await auth_client.get(SETTINGS)
    assert response.status_code == 200, response.text

    payload = json.dumps(response.json())
    for value in secrets.values():
        assert value not in payload
    assert settings.secret_key not in payload

    integrations = {item["key"]: item for item in response.json()["integrations"]}
    assert integrations["pagespeed"]["configured"] is True
    assert integrations["search_console"]["configured"] is True


async def test_identifies_the_authenticated_user(client: AsyncClient, other_user: User) -> None:
    """Cada cuenta ve su propia identidad, nunca la de otra."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": other_user.email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]

    response = await client.get(SETTINGS, headers={"Authorization": f"Bearer {token}"})
    assert response.json()["user_email"] == other_user.email
