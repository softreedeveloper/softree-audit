"""Cliente de PageSpeed Insights: caché, cuota y errores."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from softree_audit.models.enums import PageSpeedStrategy
from softree_audit.services.performance.client import (
    API_URL,
    PageSpeedClient,
    PageSpeedError,
    PageSpeedQuotaError,
    PageSpeedTargetError,
    cache_key,
)

from tests.fixtures import pagespeed

pytestmark = pytest.mark.unit

URL = "https://softree.mx/"


class FakeRedis:
    """Doble mínimo de Redis para verificar la caché."""

    def __init__(self, *, broken: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.broken = broken

    async def get(self, key: str) -> str | None:
        if self.broken:
            from redis.exceptions import RedisError

            raise RedisError("caído")
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        if self.broken:
            from redis.exceptions import RedisError

            raise RedisError("caído")
        self.store[key] = value


def client(**kwargs: object) -> PageSpeedClient:
    return PageSpeedClient("clave-de-prueba", **kwargs)  # type: ignore[arg-type]


@respx.mock
async def test_successful_analysis() -> None:
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=pagespeed.response()))

    async with client() as psi:
        payload, from_cache = await psi.analyze(URL, PageSpeedStrategy.MOBILE)

    assert from_cache is False
    assert payload["lighthouseResult"]["lighthouseVersion"] == "12.2.1"

    params = route.calls[0].request.url.params
    assert params["url"] == URL
    assert params["strategy"] == "mobile"
    assert params["key"] == "clave-de-prueba"


@respx.mock
async def test_all_four_categories_are_requested() -> None:
    """Sin pedirlas explícitamente, PSI solo devuelve rendimiento."""
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=pagespeed.response()))

    async with client() as psi:
        await psi.analyze(URL, PageSpeedStrategy.MOBILE)

    categories = route.calls[0].request.url.params.get_list("category")
    assert set(categories) == {"performance", "accessibility", "best-practices", "seo"}


@respx.mock
async def test_works_without_api_key() -> None:
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=pagespeed.response()))

    async with PageSpeedClient(None) as psi:
        await psi.analyze(URL, PageSpeedStrategy.MOBILE)

    assert "key" not in route.calls[0].request.url.params


@respx.mock
async def test_quota_error_is_distinguished() -> None:
    """La cuota agotada debe poder explicarse al usuario, no ser un error genérico."""
    respx.get(API_URL).mock(return_value=httpx.Response(429, json=pagespeed.quota_error()))

    async with client() as psi:
        with pytest.raises(PageSpeedQuotaError) as excinfo:
            await psi.analyze(URL, PageSpeedStrategy.MOBILE)

    assert excinfo.value.reason == "quota_exceeded"
    assert "PAGESPEED_API_KEY" in str(excinfo.value)


@respx.mock
async def test_unreachable_target_is_distinguished() -> None:
    """Google no puede analizar un sitio que no es público."""
    respx.get(API_URL).mock(
        return_value=httpx.Response(400, json=pagespeed.unreachable_target_error())
    )

    async with client() as psi:
        with pytest.raises(PageSpeedTargetError) as excinfo:
            await psi.analyze(URL, PageSpeedStrategy.MOBILE)

    assert excinfo.value.reason == "target_not_reachable"
    assert "accesible públicamente" in str(excinfo.value)


@respx.mock
async def test_server_error_is_reported_with_its_code() -> None:
    respx.get(API_URL).mock(return_value=httpx.Response(503, text="mantenimiento"))

    async with client() as psi:
        with pytest.raises(PageSpeedError) as excinfo:
            await psi.analyze(URL, PageSpeedStrategy.MOBILE)

    assert excinfo.value.reason == "http_503"


@respx.mock
async def test_network_failure_is_retried_and_then_reported() -> None:
    route = respx.get(API_URL).mock(side_effect=httpx.ConnectError("sin red"))

    async with client() as psi:
        with pytest.raises(PageSpeedError) as excinfo:
            await psi.analyze(URL, PageSpeedStrategy.MOBILE)

    assert excinfo.value.reason == "api_unreachable"
    # Reintentos acotados, nunca infinitos.
    assert route.call_count == 3


@respx.mock
async def test_response_without_lighthouse_result_is_rejected() -> None:
    respx.get(API_URL).mock(return_value=httpx.Response(200, json={"id": URL}))

    async with client() as psi:
        with pytest.raises(PageSpeedError) as excinfo:
            await psi.analyze(URL, PageSpeedStrategy.MOBILE)

    assert excinfo.value.reason == "invalid_response"


# ── Caché ──────────────────────────────────────────────────────────────────


@respx.mock
async def test_second_call_is_served_from_cache() -> None:
    """La cuota es limitada: no se repite una consulta ya hecha."""
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=pagespeed.response()))
    redis = FakeRedis()

    async with client(redis=redis) as psi:
        _, first = await psi.analyze(URL, PageSpeedStrategy.MOBILE)
        _, second = await psi.analyze(URL, PageSpeedStrategy.MOBILE)

    assert first is False
    assert second is True
    assert route.call_count == 1


@respx.mock
async def test_each_strategy_has_its_own_cache_entry() -> None:
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=pagespeed.response()))
    redis = FakeRedis()

    async with client(redis=redis) as psi:
        await psi.analyze(URL, PageSpeedStrategy.MOBILE)
        await psi.analyze(URL, PageSpeedStrategy.DESKTOP)

    assert route.call_count == 2
    assert len(redis.store) == 2


def test_cache_key_depends_on_url_and_strategy() -> None:
    mobile = cache_key(URL, PageSpeedStrategy.MOBILE)
    assert mobile != cache_key(URL, PageSpeedStrategy.DESKTOP)
    assert mobile != cache_key("https://otro.test/", PageSpeedStrategy.MOBILE)


@respx.mock
async def test_a_broken_cache_does_not_break_the_analysis() -> None:
    """La caché es una optimización, no una dependencia."""
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=pagespeed.response()))

    async with client(redis=FakeRedis(broken=True)) as psi:
        payload, from_cache = await psi.analyze(URL, PageSpeedStrategy.MOBILE)

    assert from_cache is False
    assert payload["lighthouseResult"]


@respx.mock
async def test_cache_can_be_disabled() -> None:
    route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=pagespeed.response()))
    redis = FakeRedis()

    async with client(redis=redis, cache_ttl_seconds=0) as psi:
        await psi.analyze(URL, PageSpeedStrategy.MOBILE)
        await psi.analyze(URL, PageSpeedStrategy.MOBILE)

    assert route.call_count == 2
    assert redis.store == {}


@respx.mock
async def test_corrupted_cache_entry_is_ignored() -> None:
    respx.get(API_URL).mock(return_value=httpx.Response(200, json=pagespeed.response()))
    redis = FakeRedis()
    redis.store[cache_key(URL, PageSpeedStrategy.MOBILE)] = "esto no es json"

    async with client(redis=redis) as psi:
        _, from_cache = await psi.analyze(URL, PageSpeedStrategy.MOBILE)

    assert from_cache is False
    assert json.loads(redis.store[cache_key(URL, PageSpeedStrategy.MOBILE)])["id"]
