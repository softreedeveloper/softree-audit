"""Motor de crawling: límites, deduplicación y cancelación."""

from __future__ import annotations

from collections.abc import Sequence

import httpx
import pytest
import respx
from softree_audit.services.common.http_client import SafeHttpClient
from softree_audit.services.common.url_guard import GuardPolicy, ScopePolicy, UrlGuard
from softree_audit.services.crawler.crawler import (
    Crawler,
    CrawlSettings,
    normalize_for_visit,
)

pytestmark = pytest.mark.unit

IP = "93.184.216.34"
HOST = "softree.mx"
BASE = f"https://{HOST}/"
# El guard normaliza la URL base y le quita la barra final.
BASE_NORMALIZED = f"https://{HOST}"
SCOPE = ScopePolicy(allowed_domains=(HOST,))


async def _resolver(host: str, port: int) -> Sequence[str]:
    return [IP]


def make_client() -> SafeHttpClient:
    return SafeHttpClient(UrlGuard(GuardPolicy(), resolver=_resolver))


def html(body: str) -> httpx.Response:
    return httpx.Response(200, html=f"<html><body>{body}</body></html>")


def page_with_links(*paths: str) -> httpx.Response:
    links = "".join(f'<a href="{path}">x</a>' for path in paths)
    return html(f"<h1>t</h1>{links}")


def settings(**kwargs: object) -> CrawlSettings:
    defaults: dict[str, object] = {"request_delay_ms": 0, "concurrency": 2}
    return CrawlSettings(**{**defaults, **kwargs})  # type: ignore[arg-type]


def mock_missing_robots_and_sitemap() -> None:
    respx.get(f"https://{IP}/robots.txt").mock(return_value=httpx.Response(404))
    respx.get(f"https://{IP}/sitemap.xml").mock(return_value=httpx.Response(404))


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://softree.mx/a", "https://softree.mx/a"),
        ("https://softree.mx/a/", "https://softree.mx/a"),
        ("https://softree.mx/a#seccion", "https://softree.mx/a"),
        ("https://softree.mx/", "https://softree.mx/"),
    ],
)
def test_visit_key_normalization(url: str, expected: str) -> None:
    assert normalize_for_visit(url) == expected


@respx.mock
async def test_crawls_the_base_url_and_follows_internal_links() -> None:
    mock_missing_robots_and_sitemap()
    respx.get(f"https://{IP}/").mock(return_value=page_with_links("/uno", "/dos"))
    respx.get(f"https://{IP}/uno").mock(return_value=html("<h1>uno</h1>"))
    respx.get(f"https://{IP}/dos").mock(return_value=html("<h1>dos</h1>"))

    async with make_client() as client:
        result = await Crawler(client, SCOPE, settings()).crawl(BASE)

    assert result.pages_crawled == 3
    assert {page.url for page in result.pages} == {
        BASE_NORMALIZED,
        f"https://{HOST}/uno",
        f"https://{HOST}/dos",
    }


@respx.mock
async def test_max_pages_is_respected() -> None:
    mock_missing_robots_and_sitemap()
    respx.get(f"https://{IP}/").mock(return_value=page_with_links("/a", "/b", "/c", "/d"))
    for path in ("a", "b", "c", "d"):
        respx.get(f"https://{IP}/{path}").mock(return_value=html("x"))

    async with make_client() as client:
        result = await Crawler(client, SCOPE, settings(max_pages=2)).crawl(BASE)

    assert result.pages_crawled == 2
    assert result.stopped_reason == "max_pages_reached"


@respx.mock
async def test_max_depth_is_respected() -> None:
    mock_missing_robots_and_sitemap()
    respx.get(f"https://{IP}/").mock(return_value=page_with_links("/nivel1"))
    respx.get(f"https://{IP}/nivel1").mock(return_value=page_with_links("/nivel2"))
    respx.get(f"https://{IP}/nivel2").mock(return_value=html("hondo"))

    async with make_client() as client:
        result = await Crawler(client, SCOPE, settings(max_depth=1)).crawl(BASE)

    urls = {page.url for page in result.pages}
    assert f"https://{HOST}/nivel1" in urls
    assert f"https://{HOST}/nivel2" not in urls


@respx.mock
async def test_loops_do_not_repeat_pages() -> None:
    """Dos páginas que se enlazan mutuamente no deben rastrearse en bucle."""
    mock_missing_robots_and_sitemap()
    respx.get(f"https://{IP}/").mock(return_value=page_with_links("/a"))
    respx.get(f"https://{IP}/a").mock(return_value=page_with_links("/", "/a", "/a#x", "/a/"))

    async with make_client() as client:
        result = await Crawler(client, SCOPE, settings()).crawl(BASE)

    assert result.pages_crawled == 2


@respx.mock
async def test_out_of_scope_links_are_not_followed() -> None:
    mock_missing_robots_and_sitemap()
    respx.get(f"https://{IP}/").mock(
        return_value=page_with_links("/interna", "https://externo.test/x")
    )
    respx.get(f"https://{IP}/interna").mock(return_value=html("ok"))
    externa = respx.get("https://externo.test/x").mock(return_value=html("no deberia"))

    async with make_client() as client:
        result = await Crawler(client, SCOPE, settings()).crawl(BASE)

    assert externa.called is False
    assert result.pages_crawled == 2


@respx.mock
async def test_robots_disallow_is_respected() -> None:
    respx.get(f"https://{IP}/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /privado")
    )
    respx.get(f"https://{IP}/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get(f"https://{IP}/").mock(return_value=page_with_links("/privado", "/publico"))
    privado = respx.get(f"https://{IP}/privado").mock(return_value=html("secreto"))
    respx.get(f"https://{IP}/publico").mock(return_value=html("ok"))

    async with make_client() as client:
        result = await Crawler(client, SCOPE, settings()).crawl(BASE)

    assert privado.called is False
    assert result.blocked_by_robots == 1
    assert result.robots_txt_found is True


@respx.mock
async def test_robots_can_be_ignored_explicitly() -> None:
    respx.get(f"https://{IP}/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /")
    )
    respx.get(f"https://{IP}/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get(f"https://{IP}/").mock(return_value=html("<h1>ok</h1>"))

    async with make_client() as client:
        result = await Crawler(client, SCOPE, settings(respect_robots=False)).crawl(BASE)

    assert result.pages_crawled == 1


@respx.mock
async def test_sitemap_urls_are_used_as_seeds() -> None:
    respx.get(f"https://{IP}/robots.txt").mock(return_value=httpx.Response(404))
    respx.get(f"https://{IP}/sitemap.xml").mock(
        return_value=httpx.Response(
            200,
            content=(
                b'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                b"<url><loc>https://softree.mx/desde-sitemap</loc></url></urlset>"
            ),
            headers={"content-type": "application/xml"},
        )
    )
    respx.get(f"https://{IP}/").mock(return_value=html("<h1>inicio</h1>"))
    respx.get(f"https://{IP}/desde-sitemap").mock(return_value=html("<h1>x</h1>"))

    async with make_client() as client:
        result = await Crawler(client, SCOPE, settings()).crawl(BASE)

    assert result.sitemap_found is True
    assert result.sitemap_urls == 1
    assert f"https://{HOST}/desde-sitemap" in {page.url for page in result.pages}


@respx.mock
async def test_error_pages_are_recorded_with_their_status() -> None:
    mock_missing_robots_and_sitemap()
    respx.get(f"https://{IP}/").mock(return_value=page_with_links("/rota"))
    respx.get(f"https://{IP}/rota").mock(return_value=httpx.Response(404, html="<h1>404</h1>"))

    async with make_client() as client:
        result = await Crawler(client, SCOPE, settings()).crawl(BASE)

    rota = next(page for page in result.pages if page.url.endswith("/rota"))
    assert rota.status_code == 404
    # Se conserva quién enlazaba a la página rota, para la regla SEO-008.
    assert rota.discovered_from == BASE_NORMALIZED


@respx.mock
async def test_a_failing_request_does_not_stop_the_crawl() -> None:
    mock_missing_robots_and_sitemap()
    respx.get(f"https://{IP}/").mock(return_value=page_with_links("/falla", "/bien"))
    respx.get(f"https://{IP}/falla").mock(side_effect=httpx.ConnectError("sin conexión"))
    respx.get(f"https://{IP}/bien").mock(return_value=html("ok"))

    async with make_client() as client:
        result = await Crawler(client, SCOPE, settings()).crawl(BASE)

    fallida = next(page for page in result.pages if page.url.endswith("/falla"))
    assert fallida.error is not None
    assert any(page.url.endswith("/bien") for page in result.pages)


@respx.mock
async def test_cancellation_stops_the_crawl() -> None:
    mock_missing_robots_and_sitemap()
    respx.get(f"https://{IP}/").mock(return_value=page_with_links("/a", "/b"))
    respx.get(f"https://{IP}/a").mock(return_value=html("a"))
    respx.get(f"https://{IP}/b").mock(return_value=html("b"))

    async def cancelled() -> bool:
        return True

    async with make_client() as client:
        result = await Crawler(client, SCOPE, settings(), is_cancelled=cancelled).crawl(BASE)

    assert result.stopped_reason == "cancelled"
    assert result.pages_crawled == 0


def test_settings_from_snapshot() -> None:
    crawl = CrawlSettings.from_snapshot(
        {"max_pages": 10, "max_depth": 2, "request_delay_ms": 50, "concurrency": 3}
    )
    assert crawl.max_pages == 10
    assert crawl.max_depth == 2
    assert crawl.request_delay_ms == 50
    assert crawl.concurrency == 3


def test_settings_from_incomplete_snapshot_uses_defaults() -> None:
    crawl = CrawlSettings.from_snapshot({})
    assert crawl.max_pages == 200
    assert crawl.respect_robots is True
