"""Endpoint de salud y cabeceras de la aplicación."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from softree_audit.version import APP_VERSION, REPORT_VERSION, SCAN_ENGINE_VERSION

pytestmark = pytest.mark.integration


async def test_health_reports_versions_and_dependencies(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["redis"] == "ok"
    assert body["app_version"] == APP_VERSION
    assert body["scan_engine_version"] == SCAN_ENGINE_VERSION
    assert body["report_version"] == REPORT_VERSION
    # La bandera debe ser visible para detectar una configuración peligrosa.
    assert body["ssrf_allow_private_networks"] is False


async def test_health_needs_no_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/health")).status_code == 200


async def test_security_headers_are_present(client: AsyncClient) -> None:
    """`docs/spec/security.md` §11."""
    headers = (await client.get("/api/v1/health")).headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in headers["content-security-policy"]


async def test_request_id_is_returned_and_echoed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.headers["x-request-id"]
    assert response.headers["x-app-version"] == APP_VERSION

    provided = await client.get("/api/v1/health", headers={"X-Request-ID": "abc123"})
    assert provided.headers["x-request-id"] == "abc123"


async def test_openapi_is_served(client: AsyncClient) -> None:
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Softree Audit API"
    assert "/api/v1/auth/login" in schema["paths"]


async def test_unknown_route_uses_the_common_error_format(client: AsyncClient) -> None:
    response = await client.get("/api/v1/no-existe")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
