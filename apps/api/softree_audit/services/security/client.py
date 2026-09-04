"""Cliente de la API de OWASP ZAP.

ZAP corre como demonio en su propio contenedor, sin puertos publicados al host,
y se controla por su API HTTP con `apikey` (`docs/spec/security.md` §9).

El cliente no decide política: solo habla con ZAP. Las reglas de alcance y el
flujo del scan viven en `scanner.py`.
"""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any

import httpx

from softree_audit.core.logging import get_logger
from softree_audit.services.common.retry import with_retry

logger = get_logger(__name__)

# Errores transitorios que sí merecen un reintento acotado.
TRANSIENT_ERRORS = (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError)


class ZapError(Exception):
    """ZAP respondió con un error o no está disponible."""


class ZapUnavailableError(ZapError):
    """No se pudo contactar con ZAP."""


class ZapClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        *,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            trust_env=False,
        )

    async def __aenter__(self) -> ZapClient:
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

    async def _call(self, path: str, **params: Any) -> dict[str, Any]:
        query = {key: value for key, value in params.items() if value is not None}
        if self._api_key:
            query["apikey"] = self._api_key

        async def request() -> httpx.Response:
            return await self._client.get(path, params=query)

        try:
            response = await with_retry(
                request, retry_on=TRANSIENT_ERRORS, attempts=3, name=f"zap{path}"
            )
        except TRANSIENT_ERRORS as exc:
            raise ZapUnavailableError(f"No fue posible contactar con ZAP: {exc}") from exc

        if response.status_code >= 400:
            raise ZapError(f"ZAP respondió {response.status_code} en {path}: {response.text[:300]}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ZapError(f"Respuesta no interpretable de ZAP en {path}") from exc

        if not isinstance(payload, dict):
            raise ZapError(f"Respuesta inesperada de ZAP en {path}")
        return payload

    # ── Estado ─────────────────────────────────────────────────────────────

    async def version(self) -> str:
        payload = await self._call("/JSON/core/view/version/")
        return str(payload.get("version", "desconocida"))

    async def is_available(self) -> bool:
        try:
            await self.version()
        except ZapError:
            return False
        return True

    # ── Contexto ───────────────────────────────────────────────────────────

    async def new_context(self, name: str) -> str:
        payload = await self._call("/JSON/context/action/newContext/", contextName=name)
        return str(payload.get("contextId", ""))

    async def include_in_context(self, name: str, regex: str) -> None:
        await self._call("/JSON/context/action/includeInContext/", contextName=name, regex=regex)

    async def exclude_from_context(self, name: str, regex: str) -> None:
        await self._call("/JSON/context/action/excludeFromContext/", contextName=name, regex=regex)

    async def remove_context(self, name: str) -> None:
        await self._call("/JSON/context/action/removeContext/", contextName=name)

    # ── Tráfico ────────────────────────────────────────────────────────────

    async def access_url(self, url: str, *, follow_redirects: bool = False) -> None:
        """Pide a ZAP que descargue una URL. El passive scan analiza la respuesta."""
        await self._call(
            "/JSON/core/action/accessUrl/",
            url=url,
            followRedirects="true" if follow_redirects else "false",
        )

    async def spider_scan(
        self, url: str, *, context_name: str, max_children: int, recurse: bool = True
    ) -> str:
        payload = await self._call(
            "/JSON/spider/action/scan/",
            url=url,
            contextName=context_name,
            maxChildren=str(max_children),
            recurse="true" if recurse else "false",
        )
        return str(payload.get("scan", ""))

    async def spider_status(self, scan_id: str) -> int:
        payload = await self._call("/JSON/spider/view/status/", scanId=scan_id)
        return int(payload.get("status", 0))

    async def stop_spider(self, scan_id: str) -> None:
        await self._call("/JSON/spider/action/stop/", scanId=scan_id)

    async def spider_results(self, scan_id: str) -> list[str]:
        payload = await self._call("/JSON/spider/view/results/", scanId=scan_id)
        raw = payload.get("results", [])
        if not isinstance(raw, list):
            return []
        return [str(item) for item in raw]

    # ── Passive scan ───────────────────────────────────────────────────────

    async def set_passive_scan_enabled(self, enabled: bool) -> None:
        await self._call("/JSON/pscan/action/setEnabled/", enabled="true" if enabled else "false")

    async def records_to_scan(self) -> int:
        payload = await self._call("/JSON/pscan/view/recordsToScan/")
        return int(payload.get("recordsToScan", 0))

    async def wait_for_passive_scan(
        self, *, timeout_seconds: float, poll_seconds: float = 1.0
    ) -> bool:
        """Espera a que se vacíe la cola del passive scan.

        Devuelve `False` si se agota el tiempo: el análisis sigue con las
        alertas disponibles en lugar de perder todo el trabajo.
        """
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            pending = await self.records_to_scan()
            if pending == 0:
                return True
            if asyncio.get_running_loop().time() >= deadline:
                logger.warning("zap.passive_scan_timeout", pending=pending)
                return False
            await asyncio.sleep(poll_seconds)

    # ── Alertas ────────────────────────────────────────────────────────────

    async def alerts(
        self, *, base_url: str | None = None, start: int = 0, count: int = 500
    ) -> list[dict[str, Any]]:
        payload = await self._call(
            "/JSON/core/view/alerts/",
            baseurl=base_url,
            start=str(start),
            count=str(count),
        )
        raw = payload.get("alerts", [])
        if not isinstance(raw, list):
            return []
        return [alert for alert in raw if isinstance(alert, dict)]

    async def all_alerts(
        self, *, base_url: str | None = None, limit: int = 5000
    ) -> list[dict[str, Any]]:
        """Recorre las alertas por páginas hasta agotarlas o llegar al límite."""
        collected: list[dict[str, Any]] = []
        page_size = 500
        while len(collected) < limit:
            batch = await self.alerts(base_url=base_url, start=len(collected), count=page_size)
            if not batch:
                break
            collected.extend(batch)
            if len(batch) < page_size:
                break
        return collected[:limit]

    async def delete_all_alerts(self) -> None:
        await self._call("/JSON/core/action/deleteAllAlerts/")

    async def new_session(self, name: str) -> None:
        """Sesión limpia: evita arrastrar alertas de un scan anterior."""
        await self._call("/JSON/core/action/newSession/", name=name, overwrite="true")
