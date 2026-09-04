"""Sincronización de métricas de Search Console.

Recorre los periodos y dimensiones pedidos y devuelve las filas ya listas para
persistir. No escribe en base de datos: el orquestador persiste.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from softree_audit.core.logging import get_logger
from softree_audit.models.enums import SearchConsoleDimension, SearchConsolePeriod
from softree_audit.services.search_console.client import (
    MetricRow,
    SearchConsoleClient,
    SearchConsoleError,
    period_range,
)

logger = get_logger(__name__)

DEFAULT_PERIODS = (
    SearchConsolePeriod.LAST_7_DAYS,
    SearchConsolePeriod.LAST_28_DAYS,
    SearchConsolePeriod.LAST_90_DAYS,
)
DEFAULT_DIMENSIONS = (
    SearchConsoleDimension.DATE,
    SearchConsoleDimension.QUERY,
    SearchConsoleDimension.PAGE,
    SearchConsoleDimension.COUNTRY,
    SearchConsoleDimension.DEVICE,
)

# Las dimensiones de alta cardinalidad se acotan; `date` necesita todas sus filas.
ROW_LIMITS: dict[SearchConsoleDimension, int] = {
    SearchConsoleDimension.DATE: 100,
    SearchConsoleDimension.QUERY: 500,
    SearchConsoleDimension.PAGE: 500,
    SearchConsoleDimension.COUNTRY: 100,
    SearchConsoleDimension.DEVICE: 10,
}


@dataclass(slots=True)
class SyncedMetric:
    period: SearchConsolePeriod
    row: MetricRow


@dataclass(slots=True)
class SearchConsoleAnalysis:
    property_url: str
    metrics: list[SyncedMetric] = field(default_factory=list)
    totals: dict[str, Any] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        by_period: dict[str, int] = {}
        for metric in self.metrics:
            by_period[metric.period.value] = by_period.get(metric.period.value, 0) + 1
        return {
            "property_url": self.property_url,
            "rows": len(self.metrics),
            "rows_by_period": by_period,
            "totals": self.totals,
            "failures": self.failures,
        }


def _totals(metrics: list[SyncedMetric]) -> dict[str, Any]:
    """Totales por periodo, calculados sobre la dimensión `date`.

    Sumar sobre `query` o `page` daría cifras infladas: Search Console omite
    filas por privacidad y una misma visita aparece en varias dimensiones.
    """
    totals: dict[str, Any] = {}
    for period in DEFAULT_PERIODS:
        rows = [
            metric.row
            for metric in metrics
            if metric.period is period and metric.row.dimension is SearchConsoleDimension.DATE
        ]
        if not rows:
            continue
        clicks = sum(row.clicks for row in rows)
        impressions = sum(row.impressions for row in rows)
        totals[period.value] = {
            "clicks": clicks,
            "impressions": impressions,
            "ctr": round(clicks / impressions, 6) if impressions else 0.0,
            "position": (
                round(sum(row.position * row.impressions for row in rows) / impressions, 2)
                if impressions
                else None
            ),
            "days": len(rows),
        }
    return totals


async def sync(
    client: SearchConsoleClient,
    property_url: str,
    *,
    periods: tuple[SearchConsolePeriod, ...] = DEFAULT_PERIODS,
    dimensions: tuple[SearchConsoleDimension, ...] = DEFAULT_DIMENSIONS,
    today: dt.date | None = None,
    is_cancelled: Callable[[], Awaitable[bool]] | None = None,
) -> SearchConsoleAnalysis:
    analysis = SearchConsoleAnalysis(property_url=property_url)

    for period in periods:
        for dimension in dimensions:
            if is_cancelled and await is_cancelled():
                analysis.failures[f"{period.value}:{dimension.value}"] = "cancelled"
                return analysis
            try:
                rows = await client.search_analytics(
                    property_url,
                    dimension=dimension,
                    period=period,
                    today=today,
                    row_limit=ROW_LIMITS.get(dimension, 500),
                )
            except SearchConsoleError as exc:
                # Una combinación que falla no invalida el resto de la sincronización.
                key = f"{period.value}:{dimension.value}"
                analysis.failures[key] = exc.reason
                logger.info(
                    "search_console.query_failed",
                    period=period.value,
                    dimension=dimension.value,
                    reason=exc.reason,
                )
                continue

            analysis.metrics.extend(SyncedMetric(period=period, row=row) for row in rows)

    analysis.totals = _totals(analysis.metrics)
    window = period_range(DEFAULT_PERIODS[0], today=today)
    logger.info(
        "search_console.synced",
        property_url=property_url,
        rows=len(analysis.metrics),
        window_end=window.end.isoformat(),
    )
    return analysis
