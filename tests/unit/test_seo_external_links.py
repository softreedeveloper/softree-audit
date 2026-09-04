"""Comprobación de enlaces externos (SEO-009)."""

from __future__ import annotations

from collections.abc import Sequence

import httpx
import pytest
import respx
from softree_audit.services.common.http_client import SafeHttpClient
from softree_audit.services.common.url_guard import GuardPolicy, UrlGuard
from softree_audit.services.crawler.models import Link, PageData
from softree_audit.services.seo.external_links import check_external_links, collect_external_links

pytestmark = pytest.mark.unit

IP = "93.184.216.34"


async def _resolver(host: str, port: int) -> Sequence[str]:
    return [IP]


def make_client() -> SafeHttpClient:
    return SafeHttpClient(UrlGuard(GuardPolicy(), resolver=_resolver))


def page_with(*links: Link) -> PageData:
    return PageData(url="https://softree.mx/", depth=0, links=list(links))


def test_collects_unique_external_links_with_their_origin() -> None:
    pages = [
        page_with(
            Link(url="https://externo.test/a", text="a", is_internal=False),
            Link(url="https://externo.test/a#x", text="a otra vez", is_internal=False),
            Link(url="https://softree.mx/interna", text="interna", is_internal=True),
            Link(url="mailto:hola@softree.mx", text="correo", is_internal=False),
        )
    ]
    collected = collect_external_links(pages)
    assert collected == [("https://externo.test/a", "https://softree.mx/")]


def test_collection_respects_the_limit() -> None:
    links = [
        Link(url=f"https://externo.test/{index}", text="x", is_internal=False)
        for index in range(10)
    ]
    assert len(collect_external_links([page_with(*links)], limit=3)) == 3


@respx.mock
async def test_uses_head_and_reports_the_status() -> None:
    route = respx.head(f"https://{IP}/roto").mock(return_value=httpx.Response(404))
    pages = [page_with(Link(url="https://externo.test/roto", text="x", is_internal=False))]

    async with make_client() as client:
        results = await check_external_links(client, pages)

    assert route.called
    assert results[0].status_code == 404
    assert results[0].is_broken is True


@respx.mock
async def test_falls_back_to_get_when_head_is_not_supported() -> None:
    respx.head(f"https://{IP}/x").mock(return_value=httpx.Response(405))
    get_route = respx.get(f"https://{IP}/x").mock(return_value=httpx.Response(200))
    pages = [page_with(Link(url="https://externo.test/x", text="x", is_internal=False))]

    async with make_client() as client:
        results = await check_external_links(client, pages)

    assert get_route.called
    assert results[0].status_code == 200
    assert results[0].is_broken is False


@respx.mock
async def test_a_network_failure_is_not_reported_as_broken() -> None:
    """Un timeout no prueba que el enlace esté roto."""
    respx.head(f"https://{IP}/lento").mock(side_effect=httpx.ConnectTimeout("lento"))
    pages = [page_with(Link(url="https://externo.test/lento", text="x", is_internal=False))]

    async with make_client() as client:
        results = await check_external_links(client, pages)

    assert results[0].status_code is None
    assert results[0].is_broken is False
    assert results[0].error is not None


@pytest.mark.security
@respx.mock
async def test_external_check_still_respects_the_network_guard() -> None:
    """Un enlace hacia una IP interna sigue bloqueado aunque sea externo al scope."""

    async def private_resolver(host: str, port: int) -> Sequence[str]:
        return ["127.0.0.1"]

    client = SafeHttpClient(UrlGuard(GuardPolicy(), resolver=private_resolver))
    pages = [page_with(Link(url="https://interno.test/admin", text="x", is_internal=False))]

    async with client:
        results = await check_external_links(client, pages)

    assert results[0].status_code is None
    assert results[0].error == "bloqueado: blocked_network"
    assert results[0].is_broken is False
