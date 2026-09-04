"""Módulos del pipeline implementados hasta ahora.

El registro crece con cada slice. Un módulo que todavía no existe no genera
fila: la interfaz muestra lo que realmente se ejecutó, sin pasos ficticios.
"""

from __future__ import annotations

from softree_audit.core.config import Settings
from softree_audit.core.logging import get_logger
from softree_audit.models.enums import ModuleName, PageSpeedStrategy, ScanType
from softree_audit.scans.contracts import ModuleResult, ScanContext, ScanModule
from softree_audit.services.common.http_client import SafeHttpClient
from softree_audit.services.common.url_guard import GuardPolicy, UrlGuard
from softree_audit.services.crawler.crawler import Crawler, CrawlSettings
from softree_audit.services.crawler.models import CrawlResult
from softree_audit.services.performance.client import (
    PageSpeedClient,
    PageSpeedError,
)
from softree_audit.services.performance.engine import analyze as analyze_performance
from softree_audit.services.performance.models import PageSpeedResult
from softree_audit.services.performance.normalizer import normalize as normalize_pagespeed
from softree_audit.services.search_console.client import SearchConsoleClient
from softree_audit.services.search_console.sync import sync as sync_search_console
from softree_audit.services.security.client import ZapClient, ZapUnavailableError
from softree_audit.services.security.scanner import (
    SecuritySettings,
    ZapScanner,
)
from softree_audit.services.seo.context import SeoContext
from softree_audit.services.seo.engine import analyze
from softree_audit.services.seo.external_links import check_external_links

logger = get_logger(__name__)


def build_guard(settings: Settings) -> UrlGuard:
    return UrlGuard(
        GuardPolicy(
            allowed_ports=tuple(settings.ssrf_allowed_ports),
            allow_private_networks=settings.ssrf_allow_private_networks,
        )
    )


class DiscoveryModule:
    """Comprueba que el objetivo es alcanzable antes de gastar tiempo en él."""

    name = ModuleName.DISCOVERY

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(self, context: ScanContext) -> ModuleResult:
        guard = build_guard(self._settings)
        target = await guard.validate(context.base_url, scope=context.scope)

        crawl_settings = CrawlSettings.from_snapshot(context.scope_snapshot)
        async with SafeHttpClient(
            guard,
            timeout_seconds=float(context.scope_snapshot.get("timeout_seconds", 20)),
            max_response_bytes=self._settings.max_response_bytes,
        ) as client:
            response = await client.fetch(target.url, scope=context.scope)

        detail = {
            "resolved_ip": str(target.ip),
            "status_code": response.status_code,
            "content_type": response.content_type,
            "redirects": len(response.redirect_chain),
            "final_url": response.url,
            "max_pages": crawl_settings.max_pages,
            "max_depth": crawl_settings.max_depth,
        }
        logger.info("discovery.completed", scan_id=str(context.scan_id), **detail)
        return ModuleResult(artifact=detail, detail=detail)


class CrawlerModule:
    """Recorre el sitio dentro del alcance autorizado."""

    name = ModuleName.CRAWLER

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(self, context: ScanContext) -> ModuleResult:
        guard = build_guard(self._settings)
        crawl_settings = CrawlSettings.from_snapshot(context.scope_snapshot)

        async with SafeHttpClient(
            guard,
            timeout_seconds=float(context.scope_snapshot.get("timeout_seconds", 20)),
            max_response_bytes=self._settings.max_response_bytes,
        ) as client:
            crawler = Crawler(
                client,
                context.scope,
                crawl_settings,
                is_cancelled=context.is_cancelled,
            )
            result = await crawler.crawl(context.base_url)

        # Un crawl en el que todas las peticiones fueron bloqueadas no es un
        # éxito con cero páginas: informarlo como `completed` haría creer que el
        # sitio no tiene contenido.
        usable = [
            page for page in result.pages if page.status_code is not None and page.error is None
        ]
        if not usable and result.blocked_by_guard:
            raise RuntimeError(
                f"El guard bloqueó las {result.blocked_by_guard} peticiones del crawl. "
                "Revise el alcance del sitio y la configuración de red."
            )

        return ModuleResult(artifact=result, detail=result.summary())


class SeoModule:
    """Aplica las reglas SEO-001 a SEO-016 sobre lo que produjo el crawler."""

    name = ModuleName.SEO

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(self, context: ScanContext) -> ModuleResult:
        crawl = context.artifact(ModuleName.CRAWLER)
        if not isinstance(crawl, CrawlResult) or not crawl.pages:
            # Sin datos del crawler no hay nada que analizar; decirlo es más
            # honesto que devolver un análisis vacío como si fuera un resultado.
            return ModuleResult(skipped=True, skip_reason="sin_paginas_rastreadas")

        seo_context = SeoContext(
            crawl=crawl,
            base_url=context.base_url,
            allowed_domains=context.scope.allowed_domains,
        )

        if context.scope_snapshot.get("check_external_links"):
            guard = build_guard(self._settings)
            async with SafeHttpClient(
                guard,
                timeout_seconds=float(context.scope_snapshot.get("timeout_seconds", 20)),
                max_response_bytes=self._settings.max_response_bytes,
            ) as client:
                seo_context.external_checks = await check_external_links(
                    client, crawl.pages, is_cancelled=context.is_cancelled
                )

        analysis = analyze(seo_context)
        logger.info("seo.completed", scan_id=str(context.scan_id), **analysis.summary())
        return ModuleResult(artifact=analysis, detail=analysis.summary())


class SecurityModule:
    """Passive scan con OWASP ZAP (ADR-004).

    Si ZAP no está configurado o no responde, el módulo se marca `skipped` con
    el motivo: es una integración externa y su ausencia no debe hacer fracasar
    la auditoría completa.
    """

    name = ModuleName.SECURITY

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(self, context: ScanContext) -> ModuleResult:
        if not self._settings.zap_url:
            return ModuleResult(skipped=True, skip_reason="zap_no_configurado")

        crawl = context.artifact(ModuleName.CRAWLER)
        urls: tuple[str, ...] = (context.base_url,)
        if isinstance(crawl, CrawlResult) and crawl.pages:
            urls = tuple(
                page.url
                for page in crawl.pages
                if page.status_code is not None and page.error is None
            ) or (context.base_url,)

        snapshot = context.scope_snapshot
        security_settings = SecuritySettings(
            base_url=context.base_url,
            allowed_domains=context.scope.allowed_domains,
            excluded_paths=context.scope.excluded_paths,
            urls=urls,
            spider_enabled=bool(snapshot.get("zap_spider_enabled", True)),
            max_pages=int(snapshot.get("max_pages", 200)),
            request_delay_ms=int(snapshot.get("request_delay_ms", 200)),
            timeout_seconds=float(self._settings.zap_timeout_seconds),
        )

        async with ZapClient(
            self._settings.zap_url,
            self._settings.zap_api_key,
            timeout_seconds=min(float(self._settings.zap_timeout_seconds), 120.0),
        ) as client:
            try:
                if not await client.is_available():
                    return ModuleResult(skipped=True, skip_reason="zap_no_disponible")
            except ZapUnavailableError:
                return ModuleResult(skipped=True, skip_reason="zap_no_disponible")

            scanner = ZapScanner(client, security_settings, is_cancelled=context.is_cancelled)
            analysis = await scanner.run(context.scan_id)

        return ModuleResult(artifact=analysis, detail=analysis.summary())


class PerformanceModule:
    """Google PageSpeed Insights sobre la URL base, en móvil y escritorio.

    Se analiza la URL base y no todo el sitio: cada llamada consume cuota y
    tarda decenas de segundos. Ampliar el conjunto de páginas es una decisión
    de producto que puede tomarse después sin cambiar el módulo.
    """

    name = ModuleName.PERFORMANCE

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(self, context: ScanContext) -> ModuleResult:
        strategies = (PageSpeedStrategy.MOBILE, PageSpeedStrategy.DESKTOP)
        results: list[PageSpeedResult] = []
        failures: dict[str, str] = {}

        async with PageSpeedClient(
            self._settings.pagespeed_api_key,
            redis=context.redis,
            cache_ttl_seconds=self._settings.pagespeed_cache_ttl_seconds,
        ) as client:
            for strategy in strategies:
                if await context.is_cancelled():
                    failures[strategy.value] = "cancelled"
                    break
                try:
                    payload, from_cache = await client.analyze(context.base_url, strategy)
                except PageSpeedError as exc:
                    # Una estrategia que falla no invalida la otra.
                    logger.warning(
                        "pagespeed.failed",
                        scan_id=str(context.scan_id),
                        strategy=strategy.value,
                        reason=exc.reason,
                        error=str(exc),
                    )
                    failures[strategy.value] = exc.reason
                    continue

                result = normalize_pagespeed(payload, url=context.base_url, strategy=strategy)
                result.from_cache = from_cache
                results.append(result)

        if not results:
            # Sin ningún resultado no hay nada que reportar; el motivo se
            # registra para que la interfaz pueda explicarlo.
            return ModuleResult(
                skipped=True,
                skip_reason=next(iter(failures.values()), "sin_resultados"),
                detail={"failures": failures},
            )

        analysis = analyze_performance(results)
        analysis.failures = failures
        logger.info("pagespeed.completed", scan_id=str(context.scan_id), **analysis.summary())
        return ModuleResult(artifact=analysis, detail=analysis.summary())


class SearchConsoleModule:
    """Sincroniza las métricas de Search Console del proyecto del sitio.

    Si el proyecto no tiene conexión, el módulo queda `skipped` y el resto de la
    auditoría continúa con normalidad: no estar conectado no es un error (§23).
    """

    name = ModuleName.SEARCH_CONSOLE

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def run(self, context: ScanContext) -> ModuleResult:
        if context.search_console is None:
            return ModuleResult(skipped=True, skip_reason="no_conectado")

        access_token, property_url = context.search_console
        if not property_url:
            return ModuleResult(skipped=True, skip_reason="sin_propiedad_seleccionada")

        async with SearchConsoleClient(access_token) as client:
            analysis = await sync_search_console(
                client, property_url, is_cancelled=context.is_cancelled
            )

        if not analysis.metrics and analysis.failures:
            return ModuleResult(
                skipped=True,
                skip_reason=next(iter(analysis.failures.values())),
                detail=analysis.summary(),
            )

        logger.info("search_console.completed", scan_id=str(context.scan_id), **analysis.summary())
        return ModuleResult(artifact=analysis, detail=analysis.summary())


# Módulos aplicables a cada tipo de scan. Las entradas de scoring y reportes
# se añaden en los Slices 8 a 10.
MODULES_BY_SCAN_TYPE: dict[ScanType, tuple[ModuleName, ...]] = {
    ScanType.FULL: (
        ModuleName.DISCOVERY,
        ModuleName.CRAWLER,
        ModuleName.SEO,
        ModuleName.SECURITY,
        ModuleName.PERFORMANCE,
        ModuleName.SEARCH_CONSOLE,
    ),
    ScanType.SEO: (
        ModuleName.DISCOVERY,
        ModuleName.CRAWLER,
        ModuleName.SEO,
        ModuleName.SEARCH_CONSOLE,
    ),
    ScanType.SECURITY: (ModuleName.DISCOVERY, ModuleName.CRAWLER, ModuleName.SECURITY),
    ScanType.PERFORMANCE: (ModuleName.DISCOVERY, ModuleName.PERFORMANCE),
}


def build_registry(settings: Settings) -> dict[ModuleName, ScanModule]:
    return {
        ModuleName.DISCOVERY: DiscoveryModule(settings),
        ModuleName.CRAWLER: CrawlerModule(settings),
        ModuleName.SEO: SeoModule(settings),
        ModuleName.SECURITY: SecurityModule(settings),
        ModuleName.PERFORMANCE: PerformanceModule(settings),
        ModuleName.SEARCH_CONSOLE: SearchConsoleModule(settings),
    }


def modules_for(scan_type: ScanType) -> tuple[ModuleName, ...]:
    return MODULES_BY_SCAN_TYPE.get(scan_type, (ModuleName.DISCOVERY,))


def module_timeout_seconds(name: ModuleName, settings: Settings) -> float:
    """Tiempo máximo de cada módulo (`docs/spec/architecture.md` §3).

    ZAP es la integración que más puede tardar y tiene su propio límite; el
    resto se acota con el timeout global del scan.
    """
    if name is ModuleName.SECURITY:
        # Margen sobre el límite interno del scanner, para que sea este quien
        # cierre ordenadamente en lugar de cortarse desde fuera.
        return float(settings.zap_timeout_seconds) + 120.0
    if name is ModuleName.PERFORMANCE:
        # Dos estrategias, cada una con su propio timeout de petición y sus
        # reintentos.
        return 600.0
    return float(settings.scan_timeout_seconds)
