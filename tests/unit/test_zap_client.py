"""Cliente y flujo de ZAP, contra un doble de su API."""

from __future__ import annotations

import httpx
import pytest
import respx
from softree_audit.services.security.client import ZapClient, ZapError, ZapUnavailableError
from softree_audit.services.security.scanner import SecuritySettings, ZapScanner

pytestmark = pytest.mark.unit

ZAP = "http://zap:8080"


def client() -> ZapClient:
    return ZapClient(ZAP, "clave-de-prueba", timeout_seconds=5.0)


def settings(**overrides: object) -> SecuritySettings:
    defaults: dict[str, object] = {
        "base_url": "https://softree.mx",
        "allowed_domains": ("softree.mx",),
        "excluded_paths": (),
        "urls": ("https://softree.mx/", "https://softree.mx/blog"),
        "spider_enabled": False,
        "max_pages": 50,
        "request_delay_ms": 0,
        "timeout_seconds": 5.0,
    }
    return SecuritySettings(**{**defaults, **overrides})  # type: ignore[arg-type]


@respx.mock
async def test_version_and_api_key() -> None:
    route = respx.get(f"{ZAP}/JSON/core/view/version/").mock(
        return_value=httpx.Response(200, json={"version": "2.15.0"})
    )
    async with client() as zap:
        assert await zap.version() == "2.15.0"

    assert route.calls[0].request.url.params["apikey"] == "clave-de-prueba"


@respx.mock
async def test_unavailable_zap_raises_a_domain_error() -> None:
    respx.get(f"{ZAP}/JSON/core/view/version/").mock(side_effect=httpx.ConnectError("caído"))
    async with client() as zap:
        with pytest.raises(ZapUnavailableError):
            await zap.version()


@respx.mock
async def test_is_available_is_false_when_zap_does_not_answer() -> None:
    respx.get(f"{ZAP}/JSON/core/view/version/").mock(side_effect=httpx.ConnectError("caído"))
    async with client() as zap:
        assert await zap.is_available() is False


@respx.mock
async def test_http_error_from_zap_is_reported() -> None:
    respx.get(f"{ZAP}/JSON/core/view/version/").mock(
        return_value=httpx.Response(403, text="Bad API key")
    )
    async with client() as zap:
        with pytest.raises(ZapError):
            await zap.version()


@respx.mock
async def test_alerts_are_paginated() -> None:
    page_one = [{"name": f"Alerta {index}"} for index in range(500)]
    page_two = [{"name": "Alerta final"}]

    def responder(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params.get("start", 0))
        return httpx.Response(200, json={"alerts": page_one if start == 0 else page_two})

    respx.get(f"{ZAP}/JSON/core/view/alerts/").mock(side_effect=responder)

    async with client() as zap:
        alerts = await zap.all_alerts(base_url="https://softree.mx")

    assert len(alerts) == 501


@respx.mock
async def test_wait_for_passive_scan_returns_false_on_timeout() -> None:
    """Agotar el tiempo no debe perder el trabajo ya hecho."""
    respx.get(f"{ZAP}/JSON/pscan/view/recordsToScan/").mock(
        return_value=httpx.Response(200, json={"recordsToScan": "7"})
    )
    async with client() as zap:
        assert await zap.wait_for_passive_scan(timeout_seconds=0.2, poll_seconds=0.05) is False


@respx.mock
async def test_wait_for_passive_scan_returns_true_when_the_queue_drains() -> None:
    respx.get(f"{ZAP}/JSON/pscan/view/recordsToScan/").mock(
        return_value=httpx.Response(200, json={"recordsToScan": "0"})
    )
    async with client() as zap:
        assert await zap.wait_for_passive_scan(timeout_seconds=1.0) is True


def _mock_common_endpoints() -> dict[str, respx.Route]:
    """Registra los endpoints del flujo y devuelve las rutas para poder afirmar.

    Volver a registrar una ruta ya declarada la sustituye por una respuesta sin
    cuerpo, así que las pruebas reutilizan estas.
    """
    routes: dict[str, respx.Route] = {}
    for name, path in (
        ("new_session", "/JSON/core/action/newSession/"),
        ("delete_alerts", "/JSON/core/action/deleteAllAlerts/"),
        ("pscan_enable", "/JSON/pscan/action/setEnabled/"),
        ("new_context", "/JSON/context/action/newContext/"),
        ("include", "/JSON/context/action/includeInContext/"),
        ("exclude", "/JSON/context/action/excludeFromContext/"),
        ("remove_context", "/JSON/context/action/removeContext/"),
        ("access_url", "/JSON/core/action/accessUrl/"),
    ):
        routes[name] = respx.get(f"{ZAP}{path}").mock(
            return_value=httpx.Response(200, json={"Result": "OK"})
        )
    respx.get(f"{ZAP}/JSON/core/view/version/").mock(
        return_value=httpx.Response(200, json={"version": "2.15.0"})
    )
    respx.get(f"{ZAP}/JSON/pscan/view/recordsToScan/").mock(
        return_value=httpx.Response(200, json={"recordsToScan": "0"})
    )
    return routes


@respx.mock
async def test_scan_submits_the_crawled_urls_and_normalizes_alerts() -> None:
    import uuid

    routes = _mock_common_endpoints()
    access = routes["access_url"]
    respx.get(f"{ZAP}/JSON/core/view/alerts/").mock(
        return_value=httpx.Response(
            200,
            json={
                "alerts": [
                    {
                        "alertRef": "10038-1",
                        "name": "CSP no configurada",
                        "risk": "Medium",
                        "confidence": "High",
                        "url": "https://softree.mx/",
                        "cweid": "693",
                    }
                ]
            },
        )
    )

    async with client() as zap:
        analysis = await ZapScanner(zap, settings()).run(uuid.uuid4())

    assert access.call_count == 2
    assert analysis.urls_submitted == 2
    assert analysis.spider_ran is False
    assert analysis.alerts_received == 1
    assert len(analysis.findings) == 1
    assert analysis.summary()["active_scan"] is False


@respx.mock
async def test_scope_is_injected_into_the_zap_context() -> None:
    """ZAP emite sus propias peticiones: el alcance también va en su contexto."""
    import uuid

    routes = _mock_common_endpoints()
    include = routes["include"]
    exclude = routes["exclude"]
    respx.get(f"{ZAP}/JSON/core/view/alerts/").mock(
        return_value=httpx.Response(200, json={"alerts": []})
    )

    async with client() as zap:
        await ZapScanner(zap, settings(excluded_paths=("/admin",))).run(uuid.uuid4())

    assert include.called
    assert exclude.called
    assert "softree" in include.calls[0].request.url.params["regex"]
    assert "admin" in exclude.calls[0].request.url.params["regex"]


@respx.mock
async def test_context_is_removed_even_if_the_scan_fails() -> None:
    """Un contexto colgado ensucia la instancia para los siguientes scans."""
    import uuid

    routes = _mock_common_endpoints()
    remove = routes["remove_context"]
    respx.get(f"{ZAP}/JSON/core/view/alerts/").mock(return_value=httpx.Response(500, text="boom"))

    async with client() as zap:
        with pytest.raises(ZapError):
            await ZapScanner(zap, settings()).run(uuid.uuid4())

    assert remove.called


@respx.mock
async def test_cancellation_stops_submitting_urls() -> None:
    import uuid

    routes = _mock_common_endpoints()
    access = routes["access_url"]
    respx.get(f"{ZAP}/JSON/core/view/alerts/").mock(
        return_value=httpx.Response(200, json={"alerts": []})
    )

    async def cancelled() -> bool:
        return True

    async with client() as zap:
        analysis = await ZapScanner(zap, settings(), is_cancelled=cancelled).run(uuid.uuid4())

    assert access.call_count == 0
    assert analysis.urls_submitted == 0
