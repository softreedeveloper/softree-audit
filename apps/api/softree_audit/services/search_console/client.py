"""Cliente de la API de Google Search Console."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from types import TracebackType
from typing import Any

import httpx

from softree_audit.core.logging import get_logger
from softree_audit.models.enums import SearchConsoleDimension, SearchConsolePeriod
from softree_audit.services.common.retry import with_retry
from softree_audit.services.search_console.oauth import (
    OAuthError,
    RefreshTokenRevokedError,
)

logger = get_logger(__name__)

API_BASE = "https://www.googleapis.com/webmasters/v3"

# Search Console consolida los datos con dos o tres días de retraso: pedir hasta
# hoy devolvería un tramo final vacío que parecería una caída de tráfico.
DATA_LAG_DAYS = 3

MAX_ROWS_PER_DIMENSION = 1000
TRANSIENT_ERRORS = (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError)


class SearchConsoleError(Exception):
    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class MetricRow:
    dimension: SearchConsoleDimension
    dimension_value: str
    clicks: int
    impressions: int
    ctr: float
    position: float


@dataclass(frozen=True, slots=True)
class DateRange:
    start: dt.date
    end: dt.date


def period_range(period: SearchConsolePeriod, *, today: dt.date | None = None) -> DateRange:
    """Rango de fechas de un periodo, descontando el retraso de consolidación."""
    reference = today or dt.datetime.now(dt.UTC).date()
    end = reference - dt.timedelta(days=DATA_LAG_DAYS)
    start = end - dt.timedelta(days=period.days - 1)
    return DateRange(start=start, end=end)


class SearchConsoleClient:
    def __init__(self, access_token: str, *, timeout_seconds: float = 60.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"Authorization": f"Bearer {access_token}"},
            trust_env=False,
        )

    async def __aenter__(self) -> SearchConsoleClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_properties(self) -> list[dict[str, str]]:
        """Propiedades a las que la cuenta conectada tiene acceso."""
        payload = await self._request("GET", "/sites")
        entries = payload.get("siteEntry", [])
        if not isinstance(entries, list):
            return []
        return [
            {
                "site_url": str(entry.get("siteUrl", "")),
                "permission_level": str(entry.get("permissionLevel", "")),
            }
            for entry in entries
            if isinstance(entry, dict) and entry.get("siteUrl")
        ]

    async def search_analytics(
        self,
        property_url: str,
        *,
        dimension: SearchConsoleDimension,
        period: SearchConsolePeriod,
        today: dt.date | None = None,
        row_limit: int = MAX_ROWS_PER_DIMENSION,
    ) -> list[MetricRow]:
        """Consulta de Search Analytics para una dimensión y un periodo."""
        window = period_range(period, today=today)
        body = {
            "startDate": window.start.isoformat(),
            "endDate": window.end.isoformat(),
            "dimensions": [dimension.value],
            "rowLimit": row_limit,
            "dataState": "final",
        }

        # La URL de la propiedad va codificada en la ruta: puede ser un prefijo
        # con esquema (`https://sitio/`) o un dominio (`sc-domain:sitio`).
        path = f"/sites/{_quote(property_url)}/searchAnalytics/query"
        payload = await self._request("POST", path, json=body)

        rows = payload.get("rows", [])
        if not isinstance(rows, list):
            return []

        result: list[MetricRow] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            keys = row.get("keys") or []
            value = str(keys[0]) if keys else ""
            if not value:
                continue
            result.append(
                MetricRow(
                    dimension=dimension,
                    dimension_value=value[:2048],
                    clicks=int(row.get("clicks", 0)),
                    impressions=int(row.get("impressions", 0)),
                    ctr=float(row.get("ctr", 0.0)),
                    position=float(row.get("position", 0.0)),
                )
            )
        return result

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        async def call() -> httpx.Response:
            return await self._client.request(method, path, **kwargs)

        try:
            response = await with_retry(
                call, retry_on=TRANSIENT_ERRORS, attempts=3, name=f"gsc{path}"
            )
        except TRANSIENT_ERRORS as exc:
            raise SearchConsoleError(
                f"No fue posible contactar con Search Console: {exc}", reason="unreachable"
            ) from exc

        if response.status_code in (401, 403):
            raise RefreshTokenRevokedError(
                "Google denegó el acceso a la propiedad. Vuelva a conectar la cuenta."
            )
        if response.status_code == 429:
            raise SearchConsoleError(
                "Se superó el límite de consultas de Search Console.", reason="quota_exceeded"
            )
        if response.status_code >= 400:
            raise SearchConsoleError(
                f"Search Console respondió {response.status_code}.",
                reason=f"http_{response.status_code}",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise SearchConsoleError(
                "Respuesta no interpretable de Search Console.", reason="invalid_response"
            ) from exc
        return payload if isinstance(payload, dict) else {}


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


__all__ = [
    "DATA_LAG_DAYS",
    "DateRange",
    "MetricRow",
    "OAuthError",
    "SearchConsoleClient",
    "SearchConsoleError",
    "period_range",
]
