"""Cliente HTTP seguro: fijación de IP, redirects y límites de respuesta."""

from __future__ import annotations

import gzip
from collections.abc import Sequence

import httpx
import pytest
import respx
from softree_audit.services.common.http_client import (
    ResponseTooLargeError,
    SafeHttpClient,
)
from softree_audit.services.common.url_guard import (
    BlockedTargetError,
    GuardPolicy,
    ScopePolicy,
    UrlGuard,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]

PUBLIC = "93.184.216.34"
PRIVATE = "127.0.0.1"


def resolver_map(mapping: dict[str, str]):
    async def _resolve(host: str, port: int) -> Sequence[str]:
        return [mapping.get(host, PUBLIC)]

    return _resolve


def make_client(mapping: dict[str, str] | None = None, **kwargs: object) -> SafeHttpClient:
    guard = UrlGuard(GuardPolicy(), resolver=resolver_map(mapping or {}))
    return SafeHttpClient(guard, **kwargs)  # type: ignore[arg-type]


@respx.mock
async def test_request_goes_to_the_pinned_ip_with_the_original_host() -> None:
    """Cierra la ventana de DNS rebinding entre validar y conectar."""
    route = respx.get(f"https://{PUBLIC}/").mock(
        return_value=httpx.Response(200, html="<html><title>ok</title></html>")
    )

    async with make_client({"softree.mx": PUBLIC}) as client:
        response = await client.fetch("https://softree.mx/")

    assert response.status_code == 200
    assert route.called
    request = route.calls[0].request
    assert request.url.host == PUBLIC
    assert request.headers["host"] == "softree.mx"
    # La verificación TLS sigue usando el nombre real.
    assert request.extensions["sni_hostname"] == "softree.mx"
    # La URL devuelta es la lógica normalizada, no la fijada.
    assert response.url == "https://softree.mx"


@respx.mock
async def test_redirects_are_revalidated_hop_by_hop() -> None:
    respx.get(f"https://{PUBLIC}/a").mock(
        return_value=httpx.Response(302, headers={"location": "https://softree.mx/b"})
    )
    respx.get(f"https://{PUBLIC}/b").mock(return_value=httpx.Response(200, text="destino"))

    async with make_client({"softree.mx": PUBLIC}) as client:
        response = await client.fetch("https://softree.mx/a")

    assert response.status_code == 200
    assert response.url == "https://softree.mx/b"
    assert response.redirect_chain == [
        {"from": "https://softree.mx/a", "to": "https://softree.mx/b", "status": 302}
    ]


@respx.mock
async def test_redirect_to_a_private_address_is_blocked() -> None:
    """El caso clásico: destino público que redirige a la red interna."""
    respx.get(f"https://{PUBLIC}/").mock(
        return_value=httpx.Response(302, headers={"location": "http://interno.test/admin"})
    )

    async with make_client({"softree.mx": PUBLIC, "interno.test": PRIVATE}) as client:
        with pytest.raises(BlockedTargetError) as excinfo:
            await client.fetch("https://softree.mx/")

    assert excinfo.value.reason == "blocked_network"


@respx.mock
async def test_redirect_out_of_scope_is_blocked() -> None:
    respx.get(f"https://{PUBLIC}/").mock(
        return_value=httpx.Response(302, headers={"location": "https://otro.test/"})
    )
    scope = ScopePolicy(allowed_domains=("softree.mx",))

    async with make_client({"softree.mx": PUBLIC, "otro.test": PUBLIC}) as client:
        with pytest.raises(BlockedTargetError) as excinfo:
            await client.fetch("https://softree.mx/", scope=scope)

    assert excinfo.value.reason == "out_of_scope"


@respx.mock
async def test_redirect_loop_stops_at_the_limit() -> None:
    respx.get(f"https://{PUBLIC}/loop").mock(
        return_value=httpx.Response(302, headers={"location": "https://softree.mx/loop"})
    )

    async with make_client({"softree.mx": PUBLIC}) as client:
        with pytest.raises(BlockedTargetError) as excinfo:
            await client.fetch("https://softree.mx/loop")

    assert excinfo.value.reason == "too_many_redirects"


@respx.mock
async def test_oversized_response_is_truncated_not_loaded_whole() -> None:
    respx.get(f"https://{PUBLIC}/grande").mock(
        return_value=httpx.Response(200, content=b"x" * 50_000)
    )

    async with make_client({"softree.mx": PUBLIC}, max_response_bytes=1_000) as client:
        response = await client.fetch("https://softree.mx/grande")

    assert response.truncated is True
    assert len(response.content) <= 1_000


@respx.mock
async def test_compression_bomb_is_rejected() -> None:
    """Un cociente de descompresión desproporcionado agota la memoria."""
    payload = gzip.compress(b"\0" * 5_000_000)
    respx.get(f"https://{PUBLIC}/bomba").mock(
        return_value=httpx.Response(
            200,
            content=payload,
            headers={"content-encoding": "gzip", "content-type": "text/html"},
        )
    )

    async with make_client({"softree.mx": PUBLIC}, max_response_bytes=10_000_000) as client:
        with pytest.raises(ResponseTooLargeError):
            await client.fetch("https://softree.mx/bomba")


@respx.mock
async def test_content_type_is_reported() -> None:
    respx.get(f"https://{PUBLIC}/pdf").mock(
        return_value=httpx.Response(
            200, content=b"%PDF-", headers={"content-type": "application/pdf"}
        )
    )

    async with make_client({"softree.mx": PUBLIC}) as client:
        response = await client.fetch("https://softree.mx/pdf")

    assert response.content_type == "application/pdf"
    assert response.is_parseable is False


@respx.mock
async def test_user_agent_identifies_softree() -> None:
    """El target debe poder identificar y contactar a quien le escanea."""
    route = respx.get(f"https://{PUBLIC}/").mock(return_value=httpx.Response(200))

    async with make_client({"softree.mx": PUBLIC}) as client:
        await client.fetch("https://softree.mx/")

    assert "SoftreeAudit" in route.calls[0].request.headers["user-agent"]
