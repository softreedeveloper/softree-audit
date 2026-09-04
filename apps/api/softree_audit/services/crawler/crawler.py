"""Motor de crawling.

Recorrido en anchura acotado por `max_pages`, `max_depth`, concurrencia y
retardo entre peticiones. Cada URL pasa por el guard de SSRF antes de tocarse,
y el conjunto de visitadas evita bucles y duplicados (RF-06).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from softree_audit.core.logging import get_logger
from softree_audit.services.common.http_client import (
    USER_AGENT,
    ResponseTooLargeError,
    SafeHttpClient,
)
from softree_audit.services.common.url_guard import BlockedTargetError, ScopePolicy
from softree_audit.services.crawler.models import CrawlResult, Link, PageData
from softree_audit.services.crawler.parser import extract_page
from softree_audit.services.crawler.robots import (
    MAX_SITEMAP_DEPTH,
    RobotsPolicy,
    empty_robots,
    parse_robots,
    parse_sitemap,
)

logger = get_logger(__name__)

CancelCheck = Callable[[], Awaitable[bool]]


@dataclass(slots=True)
class CrawlSettings:
    """Parámetros efectivos del crawl, tomados del `scope_snapshot`."""

    max_pages: int = 200
    max_depth: int = 3
    request_delay_ms: int = 200
    concurrency: int = 4
    respect_robots: bool = True
    user_agent: str = USER_AGENT

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, object]) -> CrawlSettings:
        def integer(key: str, default: int) -> int:
            value = snapshot.get(key, default)
            return int(value) if isinstance(value, int | float | str) else default

        return cls(
            max_pages=integer("max_pages", 200),
            max_depth=integer("max_depth", 3),
            request_delay_ms=integer("request_delay_ms", 200),
            concurrency=integer("concurrency", 4),
            respect_robots=bool(snapshot.get("respect_robots", True)),
        )


def normalize_for_visit(url: str) -> str:
    """Clave de deduplicación: sin fragmento y sin barra final."""
    parts = urlsplit(url)._replace(fragment="")
    path = parts.path.rstrip("/") or "/"
    return parts._replace(path=path).geturl()


class Crawler:
    def __init__(
        self,
        client: SafeHttpClient,
        scope: ScopePolicy,
        settings: CrawlSettings,
        *,
        is_cancelled: CancelCheck | None = None,
    ) -> None:
        self._client = client
        self._scope = scope
        self._settings = settings
        self._is_cancelled = is_cancelled
        self._semaphore = asyncio.Semaphore(settings.concurrency)
        self._visited: set[str] = set()
        self._discovered: set[str] = set()

    async def crawl(self, base_url: str) -> CrawlResult:
        result = CrawlResult()

        robots = await self._load_robots(base_url)
        result.robots_txt_found = robots.found

        seeds: list[tuple[str, int, str | None]] = [(base_url, 0, None)]
        sitemap_urls = await self._load_sitemaps(base_url, robots, result)
        seeds.extend((url, 1, "sitemap.xml") for url in sitemap_urls)

        queue: list[tuple[str, int, str | None]] = []
        for url, depth, origin in seeds:
            key = normalize_for_visit(url)
            if key in self._discovered:
                continue
            self._discovered.add(key)
            queue.append((url, depth, origin))
        result.urls_discovered = len(self._discovered)

        while queue and len(result.pages) < self._settings.max_pages:
            if await self._cancelled():
                result.stopped_reason = "cancelled"
                break

            available = self._settings.max_pages - len(result.pages)
            batch = queue[: max(self._settings.concurrency, 1)][:available]
            queue = queue[len(batch) :]

            pages = await asyncio.gather(
                *(self._visit(url, depth, origin, robots, result) for url, depth, origin in batch)
            )

            for page in pages:
                if page is None:
                    continue
                result.pages.append(page)
                if page.depth >= self._settings.max_depth:
                    continue
                for link in page.links:
                    if not link.is_internal:
                        continue
                    key = normalize_for_visit(link.url)
                    if key in self._discovered:
                        continue
                    self._discovered.add(key)
                    queue.append((link.url, page.depth + 1, page.url))

        result.urls_discovered = len(self._discovered)
        if not result.stopped_reason and queue:
            result.stopped_reason = "max_pages_reached"

        logger.info("crawler.finished", base_url=base_url, **result.summary())
        return result

    # ── Internos ───────────────────────────────────────────────────────────

    async def _cancelled(self) -> bool:
        return bool(self._is_cancelled and await self._is_cancelled())

    async def _visit(
        self,
        url: str,
        depth: int,
        origin: str | None,
        robots: RobotsPolicy,
        result: CrawlResult,
    ) -> PageData | None:
        key = normalize_for_visit(url)
        if key in self._visited:
            return None
        self._visited.add(key)

        if not self._scope.permits(url):
            result.out_of_scope_skipped += 1
            return None

        if self._settings.respect_robots and not robots.allows(url, self._settings.user_agent):
            result.blocked_by_robots += 1
            logger.info("crawler.blocked_by_robots", url=url)
            return None

        async with self._semaphore:
            if self._settings.request_delay_ms:
                await asyncio.sleep(self._settings.request_delay_ms / 1000)
            try:
                response = await self._client.fetch(url, scope=self._scope)
            except BlockedTargetError as exc:
                result.blocked_by_guard += 1
                logger.info("crawler.blocked", url=url, reason=exc.reason)
                return PageData(
                    url=url, depth=depth, discovered_from=origin, error=f"bloqueado: {exc.reason}"
                )
            except ResponseTooLargeError as exc:
                return PageData(url=url, depth=depth, discovered_from=origin, error=str(exc))
            except Exception as exc:
                logger.info("crawler.fetch_failed", url=url, error=type(exc).__name__)
                return PageData(
                    url=url,
                    depth=depth,
                    discovered_from=origin,
                    error=f"{type(exc).__name__}: {exc}",
                )

        if response.redirect_chain:
            # La URL que redirige se registra por sí misma, con su cadena: es lo
            # que necesita la regla SEO-015. El contenido no se copia aquí para
            # no generar falsos duplicados de title y description; el destino se
            # encola como un enlace más y se rastrea con su propia URL.
            first_hop = response.redirect_chain[0]
            hop_status = first_hop.get("status")
            redirect_page = PageData(
                url=url,
                depth=depth,
                discovered_from=origin,
                status_code=hop_status if isinstance(hop_status, int) else None,
                response_time_ms=response.elapsed_ms,
                redirect_chain=response.redirect_chain,
            )
            redirect_page.links = [
                Link(url=response.url, text="", is_internal=self._scope.permits(response.url))
            ]
            return redirect_page

        if response.is_parseable and response.content_type in (
            "text/html",
            "application/xhtml+xml",
        ):
            page = extract_page(
                response.text(), response.url, allowed_domains=self._scope.allowed_domains
            )
        else:
            page = PageData(url=response.url, depth=depth)

        page.depth = depth
        page.discovered_from = origin
        page.status_code = response.status_code
        page.content_type = response.content_type or None
        page.response_time_ms = response.elapsed_ms
        page.content_length = len(response.content)
        page.redirect_chain = response.redirect_chain
        return page

    async def _load_robots(self, base_url: str) -> RobotsPolicy:
        url = urljoin(base_url, "/robots.txt")
        try:
            response = await self._client.fetch(url, scope=self._scope)
        except Exception as exc:
            logger.info("crawler.robots_unavailable", url=url, error=type(exc).__name__)
            return empty_robots()

        if response.status_code != 200 or not response.content:
            return empty_robots()
        return parse_robots(response.text(), base_url)

    async def _load_sitemaps(
        self, base_url: str, robots: RobotsPolicy, result: CrawlResult
    ) -> list[str]:
        candidates = list(robots.sitemaps) or [urljoin(base_url, "/sitemap.xml")]
        collected: list[str] = []
        seen_sitemaps: set[str] = set()

        for depth in range(MAX_SITEMAP_DEPTH):
            if not candidates:
                break
            next_round: list[str] = []
            for sitemap_url in candidates:
                if sitemap_url in seen_sitemaps:
                    continue
                seen_sitemaps.add(sitemap_url)

                try:
                    response = await self._client.fetch(sitemap_url, scope=self._scope)
                except Exception as exc:
                    logger.info(
                        "crawler.sitemap_unavailable",
                        url=sitemap_url,
                        error=type(exc).__name__,
                    )
                    continue

                if response.status_code != 200 or not response.content:
                    continue

                result.sitemap_found = True
                parsed = parse_sitemap(response.content, sitemap_url)
                collected.extend(url for url in parsed.urls if self._scope.permits(url))
                if depth + 1 < MAX_SITEMAP_DEPTH:
                    next_round.extend(parsed.nested_sitemaps)
            candidates = next_round

        result.sitemap_urls = len(collected)
        return collected
