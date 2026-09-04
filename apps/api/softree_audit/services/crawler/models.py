"""Estructuras del crawler.

Los módulos no escriben en base de datos: devuelven datos y el orquestador
persiste (`docs/spec/architecture.md` §3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Link:
    url: str
    text: str
    rel: str | None = None
    is_internal: bool = False


@dataclass(slots=True)
class PageData:
    """Una página rastreada, con todo lo que exige RF-06."""

    url: str
    depth: int
    discovered_from: str | None = None

    status_code: int | None = None
    content_type: str | None = None
    response_time_ms: int | None = None
    content_length: int | None = None

    title: str | None = None
    meta_description: str | None = None
    canonical: str | None = None
    meta_robots: str | None = None
    h1: list[str] = field(default_factory=list)
    h2: list[str] = field(default_factory=list)

    internal_links: int = 0
    external_links: int = 0
    images_total: int = 0
    images_missing_alt: int = 0
    scripts_total: int = 0
    forms_total: int = 0

    redirect_chain: list[dict[str, Any]] = field(default_factory=list)
    structured_data: dict[str, Any] = field(default_factory=dict)

    is_indexable: bool | None = None
    error: str | None = None

    # No se persiste: lo consume el motor SEO del Slice 4.
    links: list[Link] = field(default_factory=list)


@dataclass(slots=True)
class CrawlResult:
    pages: list[PageData] = field(default_factory=list)
    urls_discovered: int = 0
    robots_txt_found: bool = False
    sitemap_found: bool = False
    sitemap_urls: int = 0
    blocked_by_robots: int = 0
    out_of_scope_skipped: int = 0
    blocked_by_guard: int = 0
    stopped_reason: str | None = None

    @property
    def pages_crawled(self) -> int:
        return len(self.pages)

    def summary(self) -> dict[str, Any]:
        return {
            "pages_crawled": self.pages_crawled,
            "urls_discovered": self.urls_discovered,
            "robots_txt_found": self.robots_txt_found,
            "sitemap_found": self.sitemap_found,
            "sitemap_urls": self.sitemap_urls,
            "blocked_by_robots": self.blocked_by_robots,
            "out_of_scope_skipped": self.out_of_scope_skipped,
            "blocked_by_guard": self.blocked_by_guard,
            "stopped_reason": self.stopped_reason,
        }
