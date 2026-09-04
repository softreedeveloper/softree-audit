"""Cliente y sincronización de Search Console."""

from __future__ import annotations

import datetime as dt
import json

import httpx
import pytest
import respx
from softree_audit.models.enums import SearchConsoleDimension, SearchConsolePeriod
from softree_audit.services.search_console.client import (
    API_BASE,
    DATA_LAG_DAYS,
    SearchConsoleClient,
    SearchConsoleError,
    period_range,
)
from softree_audit.services.search_console.oauth import RefreshTokenRevokedError
from softree_audit.services.search_console.sync import sync

pytestmark = pytest.mark.unit

PROPERTY = "https://softree.mx/"
TODAY = dt.date(2026, 9, 3)


def analytics_url(property_url: str = PROPERTY) -> str:
    from urllib.parse import quote

    return f"{API_BASE}/sites/{quote(property_url, safe='')}/searchAnalytics/query"


def rows_response(count: int = 3) -> dict[str, object]:
    return {
        "rows": [
            {
                "keys": [f"consulta {index}"],
                "clicks": 10 - index,
                "impressions": 100 - index,
                "ctr": 0.1,
                "position": 5.5 + index,
            }
            for index in range(count)
        ]
    }


# ── Rango de fechas ────────────────────────────────────────────────────────


def test_period_range_discounts_the_consolidation_lag() -> None:
    """Pedir hasta hoy devolvería días vacíos que parecerían una caída."""
    window = period_range(SearchConsolePeriod.LAST_7_DAYS, today=TODAY)
    assert window.end == TODAY - dt.timedelta(days=DATA_LAG_DAYS)
    assert (window.end - window.start).days == 6


@pytest.mark.parametrize(
    ("period", "days"),
    [
        (SearchConsolePeriod.LAST_7_DAYS, 7),
        (SearchConsolePeriod.LAST_28_DAYS, 28),
        (SearchConsolePeriod.LAST_90_DAYS, 90),
    ],
)
def test_period_lengths(period: SearchConsolePeriod, days: int) -> None:
    window = period_range(period, today=TODAY)
    assert (window.end - window.start).days + 1 == days


# ── Cliente ────────────────────────────────────────────────────────────────


@respx.mock
async def test_list_properties() -> None:
    respx.get(f"{API_BASE}/sites").mock(
        return_value=httpx.Response(
            200,
            json={
                "siteEntry": [
                    {"siteUrl": PROPERTY, "permissionLevel": "siteOwner"},
                    {"siteUrl": "sc-domain:softree.mx", "permissionLevel": "siteFullUser"},
                    {"permissionLevel": "sin url"},
                ]
            },
        )
    )
    async with SearchConsoleClient("token") as client:
        properties = await client.list_properties()

    assert [item["site_url"] for item in properties] == [PROPERTY, "sc-domain:softree.mx"]


@respx.mock
async def test_search_analytics_sends_the_expected_query() -> None:
    route = respx.post(analytics_url()).mock(return_value=httpx.Response(200, json=rows_response()))

    async with SearchConsoleClient("token") as client:
        rows = await client.search_analytics(
            PROPERTY,
            dimension=SearchConsoleDimension.QUERY,
            period=SearchConsolePeriod.LAST_7_DAYS,
            today=TODAY,
        )

    body = json.loads(route.calls[0].request.read())
    assert body["dimensions"] == ["query"]
    # Ventana de 7 días acabando tres días antes de hoy.
    assert body["startDate"] == "2026-08-25"
    assert body["endDate"] == "2026-08-31"
    assert body["dataState"] == "final"
    assert len(rows) == 3
    assert rows[0].dimension is SearchConsoleDimension.QUERY


@respx.mock
async def test_authorization_header_is_sent() -> None:
    route = respx.get(f"{API_BASE}/sites").mock(
        return_value=httpx.Response(200, json={"siteEntry": []})
    )
    async with SearchConsoleClient("ya29.token") as client:
        await client.list_properties()
    assert route.calls[0].request.headers["authorization"] == "Bearer ya29.token"


@respx.mock
@pytest.mark.security
async def test_denied_access_is_reported_as_revoked() -> None:
    respx.get(f"{API_BASE}/sites").mock(return_value=httpx.Response(403, json={}))
    async with SearchConsoleClient("token") as client:
        with pytest.raises(RefreshTokenRevokedError):
            await client.list_properties()


@respx.mock
async def test_quota_error_is_distinguished() -> None:
    respx.post(analytics_url()).mock(return_value=httpx.Response(429, json={}))
    async with SearchConsoleClient("token") as client:
        with pytest.raises(SearchConsoleError) as excinfo:
            await client.search_analytics(
                PROPERTY,
                dimension=SearchConsoleDimension.QUERY,
                period=SearchConsolePeriod.LAST_7_DAYS,
            )
    assert excinfo.value.reason == "quota_exceeded"


@respx.mock
async def test_domain_properties_are_url_encoded() -> None:
    """`sc-domain:softree.mx` debe viajar codificado en la ruta."""
    route = respx.post(analytics_url("sc-domain:softree.mx")).mock(
        return_value=httpx.Response(200, json={"rows": []})
    )
    async with SearchConsoleClient("token") as client:
        await client.search_analytics(
            "sc-domain:softree.mx",
            dimension=SearchConsoleDimension.DEVICE,
            period=SearchConsolePeriod.LAST_7_DAYS,
        )
    assert route.called


# ── Sincronización ─────────────────────────────────────────────────────────


@respx.mock
async def test_sync_covers_every_period_and_dimension() -> None:
    respx.post(analytics_url()).mock(return_value=httpx.Response(200, json=rows_response(2)))

    async with SearchConsoleClient("token") as client:
        analysis = await sync(client, PROPERTY, today=TODAY)

    # 3 periodos por 5 dimensiones por 2 filas.
    assert len(analysis.metrics) == 30
    assert analysis.summary()["rows_by_period"]["7d"] == 10


@respx.mock
async def test_sync_totals_are_computed_from_the_date_dimension() -> None:
    """Sumar por consulta o página inflaría las cifras."""

    def responder(request: httpx.Request) -> httpx.Response:
        if json.loads(request.read())["dimensions"] == ["date"]:
            return httpx.Response(
                200,
                json={
                    "rows": [
                        {
                            "keys": ["2026-08-30"],
                            "clicks": 10,
                            "impressions": 100,
                            "ctr": 0.1,
                            "position": 4.0,
                        },
                        {
                            "keys": ["2026-08-31"],
                            "clicks": 20,
                            "impressions": 300,
                            "ctr": 0.066,
                            "position": 6.0,
                        },
                    ]
                },
            )
        return httpx.Response(200, json=rows_response(50))

    respx.post(analytics_url()).mock(side_effect=responder)

    async with SearchConsoleClient("token") as client:
        analysis = await sync(client, PROPERTY, today=TODAY)

    totals = analysis.totals["7d"]
    assert totals["clicks"] == 30
    assert totals["impressions"] == 400
    # Posición ponderada por impresiones, no media simple.
    assert totals["position"] == 5.5


@respx.mock
async def test_a_failing_combination_does_not_stop_the_sync() -> None:
    calls = {"count": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(500, json={})
        return httpx.Response(200, json=rows_response(1))

    respx.post(analytics_url()).mock(side_effect=responder)

    async with SearchConsoleClient("token") as client:
        analysis = await sync(client, PROPERTY, today=TODAY)

    assert analysis.failures
    assert len(analysis.metrics) > 0


@respx.mock
async def test_cancellation_stops_the_sync() -> None:
    respx.post(analytics_url()).mock(return_value=httpx.Response(200, json=rows_response()))

    async def cancelled() -> bool:
        return True

    async with SearchConsoleClient("token") as client:
        analysis = await sync(client, PROPERTY, today=TODAY, is_cancelled=cancelled)

    assert analysis.metrics == []
    assert "cancelled" in analysis.failures.values()
