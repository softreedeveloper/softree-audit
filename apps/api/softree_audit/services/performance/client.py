"""Cliente de Google PageSpeed Insights.

Se usa la API real (§52). Medidas para no agotar la cuota ni castigar al
objetivo:

- caché en Redis por `(url, strategy)`, configurable, seis horas por defecto;
- una petición por segundo como máximo;
- reintentos acotados solo ante errores transitorios;
- el error de cuota (429) se distingue del resto para poder degradar con un
  motivo claro.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from types import TracebackType
from typing import Any

import httpx
from redis.exceptions import RedisError

from softree_audit.core.logging import get_logger
from softree_audit.core.redis import RedisClient
from softree_audit.models.enums import PageSpeedStrategy
from softree_audit.services.common.retry import with_retry

logger = get_logger(__name__)

API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CATEGORIES = ("performance", "accessibility", "best-practices", "seo")

MIN_SECONDS_BETWEEN_CALLS = 1.0
REQUEST_TIMEOUT_SECONDS = 120.0

TRANSIENT_ERRORS = (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError)


class PageSpeedError(Exception):
    """Error normalizado de la integración con PageSpeed."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class PageSpeedQuotaError(PageSpeedError):
    """Cuota de la API agotada."""

    def __init__(self, message: str) -> None:
        super().__init__(message, reason="quota_exceeded")


class PageSpeedTargetError(PageSpeedError):
    """Google no pudo analizar la URL: normalmente no es alcanzable desde fuera."""

    def __init__(self, message: str) -> None:
        super().__init__(message, reason="target_not_reachable")


def cache_key(url: str, strategy: PageSpeedStrategy) -> str:
    digest = hashlib.sha256(f"{url}|{strategy.value}".encode()).hexdigest()[:32]
    return f"pagespeed:{digest}"


class PageSpeedClient:
    def __init__(
        self,
        api_key: str | None,
        *,
        redis: RedisClient | None = None,
        cache_ttl_seconds: int = 21600,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._redis = redis
        self._cache_ttl = cache_ttl_seconds
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds), trust_env=False)
        self._last_call_at = 0.0

    async def __aenter__(self) -> PageSpeedClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def analyze(self, url: str, strategy: PageSpeedStrategy) -> tuple[dict[str, Any], bool]:
        """Devuelve la respuesta de PSI y si vino de la caché."""
        cached = await self._read_cache(url, strategy)
        if cached is not None:
            logger.info("pagespeed.cache_hit", url=url, strategy=strategy.value)
            return cached, True

        payload = await self._request(url, strategy)
        await self._write_cache(url, strategy, payload)
        return payload, False

    # ── Internos ───────────────────────────────────────────────────────────

    async def _request(self, url: str, strategy: PageSpeedStrategy) -> dict[str, Any]:
        await self._respect_rate_limit()

        # Lista de pares y no un dict: `category` se repite una vez por categoría.
        params: list[tuple[str, str | int | float | bool | None]] = [
            ("url", url),
            ("strategy", strategy.value),
        ]
        params.extend(("category", category) for category in CATEGORIES)
        if self._api_key:
            params.append(("key", self._api_key))

        async def call() -> httpx.Response:
            return await self._client.get(API_URL, params=params)

        try:
            response = await with_retry(
                call, retry_on=TRANSIENT_ERRORS, attempts=3, name="pagespeed"
            )
        except TRANSIENT_ERRORS as exc:
            raise PageSpeedError(
                f"No fue posible contactar con PageSpeed Insights: {exc}",
                reason="api_unreachable",
            ) from exc

        return self._parse(response, url)

    def _parse(self, response: httpx.Response, url: str) -> dict[str, Any]:
        if response.status_code == 429:
            raise PageSpeedQuotaError(
                "La cuota de PageSpeed Insights está agotada. Configure PAGESPEED_API_KEY "
                "o inténtelo más tarde."
            )

        if response.status_code >= 400:
            message = self._error_message(response)
            # Google devuelve 400 cuando no puede alcanzar o renderizar la URL.
            if response.status_code == 400:
                raise PageSpeedTargetError(
                    f"PageSpeed Insights no pudo analizar «{url}»: {message}. "
                    "La URL debe ser accesible públicamente desde Internet."
                )
            raise PageSpeedError(
                f"PageSpeed Insights respondió {response.status_code}: {message}",
                reason=f"http_{response.status_code}",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise PageSpeedError(
                "Respuesta no interpretable de PageSpeed Insights", reason="invalid_response"
            ) from exc

        if not isinstance(payload, dict) or "lighthouseResult" not in payload:
            raise PageSpeedError(
                "La respuesta de PageSpeed Insights no incluye resultados de Lighthouse.",
                reason="invalid_response",
            )
        return payload

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text[:300]
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            return str(error.get("message", ""))[:300]
        return response.text[:300]

    async def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        if elapsed < MIN_SECONDS_BETWEEN_CALLS:
            await asyncio.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
        self._last_call_at = time.monotonic()

    async def _read_cache(self, url: str, strategy: PageSpeedStrategy) -> dict[str, Any] | None:
        if self._redis is None or self._cache_ttl <= 0:
            return None
        try:
            raw = await self._redis.get(cache_key(url, strategy))
        except RedisError:
            # La caché es una optimización: su fallo no debe romper el análisis.
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except ValueError:
            return None
        return payload if isinstance(payload, dict) else None

    async def _write_cache(
        self, url: str, strategy: PageSpeedStrategy, payload: dict[str, Any]
    ) -> None:
        if self._redis is None or self._cache_ttl <= 0:
            return
        try:
            await self._redis.set(cache_key(url, strategy), json.dumps(payload), ex=self._cache_ttl)
        except (RedisError, TypeError, ValueError):
            logger.info("pagespeed.cache_write_failed", url=url, strategy=strategy.value)
