"""Flujo del passive scan con OWASP ZAP.

    Site → Scope → ZAP → (Spider) → Passive Scanner → Alerts → Normalizer → Findings

Solo passive scan: no se ejecuta active scan, que genera tráfico intrusivo y
podría alterar datos del sitio del cliente (ADR-004).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from softree_audit.core.logging import get_logger
from softree_audit.services.findings.models import NormalizedFinding
from softree_audit.services.security.client import ZapClient, ZapError
from softree_audit.services.security.normalizer import normalize_alerts
from softree_audit.services.security.scope_regex import exclude_patterns, include_patterns

logger = get_logger(__name__)

MAX_ALERTS = 5000
SPIDER_POLL_SECONDS = 2.0


@dataclass(slots=True)
class SecuritySettings:
    """Parámetros efectivos del scan de seguridad."""

    base_url: str
    allowed_domains: tuple[str, ...]
    excluded_paths: tuple[str, ...]
    urls: tuple[str, ...]
    spider_enabled: bool = True
    max_pages: int = 200
    request_delay_ms: int = 200
    timeout_seconds: float = 900.0


@dataclass(slots=True)
class SecurityAnalysis:
    findings: list[NormalizedFinding] = field(default_factory=list)
    zap_version: str | None = None
    urls_submitted: int = 0
    spider_ran: bool = False
    spider_urls: int = 0
    alerts_received: int = 0
    passive_scan_completed: bool = True
    skipped_reason: str | None = None

    def summary(self) -> dict[str, Any]:
        by_severity: dict[str, int] = {}
        for finding in self.findings:
            key = finding.severity.value
            by_severity[key] = by_severity.get(key, 0) + 1
        return {
            "zap_version": self.zap_version,
            "urls_submitted": self.urls_submitted,
            "spider_ran": self.spider_ran,
            "spider_urls": self.spider_urls,
            "alerts_received": self.alerts_received,
            "findings": len(self.findings),
            "findings_by_severity": by_severity,
            "passive_scan_completed": self.passive_scan_completed,
            "active_scan": False,
        }


class ZapScanner:
    def __init__(
        self,
        client: ZapClient,
        settings: SecuritySettings,
        *,
        is_cancelled: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        self._client = client
        self._settings = settings
        self._is_cancelled = is_cancelled

    async def run(self, scan_id: uuid.UUID) -> SecurityAnalysis:
        analysis = SecurityAnalysis()
        context_name = f"softree-{scan_id}"

        analysis.zap_version = await self._client.version()
        logger.info("zap.session_start", scan_id=str(scan_id), version=analysis.zap_version)

        # Sesión limpia: sin ella se arrastrarían alertas de scans anteriores.
        await self._client.new_session(context_name)
        await self._client.delete_all_alerts()
        await self._client.set_passive_scan_enabled(True)

        try:
            await self._configure_context(context_name)
            await self._submit_urls(analysis)
            if self._settings.spider_enabled:
                await self._run_spider(context_name, analysis)

            completed = await self._client.wait_for_passive_scan(
                timeout_seconds=self._settings.timeout_seconds
            )
            analysis.passive_scan_completed = completed

            alerts = await self._client.all_alerts(
                base_url=self._settings.base_url, limit=MAX_ALERTS
            )
            analysis.alerts_received = len(alerts)
            analysis.findings = normalize_alerts(alerts)
        finally:
            # El contexto se retira siempre: dejarlo colgado ensucia la
            # instancia de ZAP para los siguientes scans.
            try:
                await self._client.remove_context(context_name)
            except ZapError:
                logger.info("zap.context_cleanup_failed", scan_id=str(scan_id))

        logger.info("zap.session_finished", scan_id=str(scan_id), **analysis.summary())
        return analysis

    # ── Etapas ─────────────────────────────────────────────────────────────

    async def _configure_context(self, context_name: str) -> None:
        """Inyecta el alcance autorizado en el propio ZAP (doble barrera)."""
        await self._client.new_context(context_name)

        includes = include_patterns(self._settings.base_url, self._settings.allowed_domains)
        for pattern in includes:
            await self._client.include_in_context(context_name, pattern)

        excludes = exclude_patterns(self._settings.allowed_domains, self._settings.excluded_paths)
        for pattern in excludes:
            await self._client.exclude_from_context(context_name, pattern)

        logger.info(
            "zap.context_configured",
            context=context_name,
            includes=len(includes),
            excludes=len(excludes),
        )

    async def _submit_urls(self, analysis: SecurityAnalysis) -> None:
        """Pide a ZAP que recorra exactamente las URL que ya rastreamos.

        Reutilizar el resultado del crawler mantiene el tráfico acotado a lo ya
        validado por el guard, en lugar de dejar que ZAP descubra por su cuenta.
        """
        delay = self._settings.request_delay_ms / 1000
        for url in self._settings.urls[: self._settings.max_pages]:
            if self._is_cancelled and await self._is_cancelled():
                logger.info("zap.cancelled_while_submitting")
                return
            try:
                await self._client.access_url(url)
                analysis.urls_submitted += 1
            except ZapError as exc:
                logger.info("zap.access_url_failed", url=url, error=str(exc))
            if delay:
                await asyncio.sleep(delay)

    async def _run_spider(self, context_name: str, analysis: SecurityAnalysis) -> None:
        """Spider de ZAP, acotado por el contexto y por `max_pages`."""
        try:
            scan_id = await self._client.spider_scan(
                self._settings.base_url,
                context_name=context_name,
                max_children=self._settings.max_pages,
            )
        except ZapError as exc:
            logger.info("zap.spider_start_failed", error=str(exc))
            return

        analysis.spider_ran = True
        deadline = asyncio.get_running_loop().time() + self._settings.timeout_seconds

        while True:
            if self._is_cancelled and await self._is_cancelled():
                await self._safe_stop_spider(scan_id)
                return
            status = await self._client.spider_status(scan_id)
            if status >= 100:
                break
            if asyncio.get_running_loop().time() >= deadline:
                logger.warning("zap.spider_timeout", scan_id=scan_id, status=status)
                await self._safe_stop_spider(scan_id)
                break
            await asyncio.sleep(SPIDER_POLL_SECONDS)

        try:
            analysis.spider_urls = len(await self._client.spider_results(scan_id))
        except ZapError:
            # El contador es informativo; su ausencia no invalida el scan.
            logger.info("zap.spider_results_unavailable", scan_id=scan_id)

    async def _safe_stop_spider(self, scan_id: str) -> None:
        try:
            await self._client.stop_spider(scan_id)
        except ZapError:
            logger.info("zap.spider_stop_failed", scan_id=scan_id)
