"""Agregados SEO del scan (`docs/spec/database.md` §seo_results)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from softree_audit.services.seo.context import SeoContext
from softree_audit.services.seo.rules import _duplicate_groups, _normalize_text


@dataclass(slots=True)
class SeoAggregates:
    pages_crawled: int = 0
    urls_discovered: int = 0
    missing_title: int = 0
    duplicate_title: int = 0
    missing_description: int = 0
    duplicate_description: int = 0
    missing_h1: int = 0
    multiple_h1: int = 0
    images_missing_alt: int = 0
    broken_internal_links: int = 0
    broken_external_links: int = 0
    missing_canonical: int = 0
    noindex_pages: int = 0
    redirect_chains: int = 0
    robots_txt_found: bool = False
    sitemap_found: bool = False
    sitemap_urls: int = 0
    structured_data_summary: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _duplicated_pages(context: SeoContext, key: str) -> int:
    """Número de páginas implicadas en algún grupo duplicado."""
    groups = _duplicate_groups(
        context.indexable_pages,
        (lambda page: page.title) if key == "title" else (lambda page: page.meta_description),
    )
    return sum(len(urls) for urls in groups.values())


def summarize_structured_data(context: SeoContext) -> dict[str, Any]:
    """Presencia de datos estructurados en el conjunto del sitio (§20)."""
    types: set[str] = set()
    with_json_ld = 0
    with_open_graph = 0
    with_twitter = 0
    invalid_json_ld = 0

    for page in context.html_pages:
        data = page.structured_data or {}
        if data.get("has_json_ld"):
            with_json_ld += 1
        if data.get("has_open_graph"):
            with_open_graph += 1
        if data.get("has_twitter"):
            with_twitter += 1
        for entry in data.get("json_ld", []) or []:
            if isinstance(entry, dict) and entry.get("valid") is False:
                invalid_json_ld += 1
        for schema_type in data.get("schema_types", []) or []:
            types.add(str(schema_type))

    total = len(context.html_pages)
    return {
        "pages_analyzed": total,
        "pages_with_json_ld": with_json_ld,
        "pages_with_open_graph": with_open_graph,
        "pages_with_twitter_cards": with_twitter,
        "invalid_json_ld_blocks": invalid_json_ld,
        "schema_types": sorted(types),
    }


def build_aggregates(context: SeoContext) -> SeoAggregates:
    html = context.html_pages
    indexable = context.indexable_pages

    return SeoAggregates(
        pages_crawled=context.crawl.pages_crawled,
        urls_discovered=context.crawl.urls_discovered,
        missing_title=sum(1 for page in html if not _normalize_text(page.title or "")),
        duplicate_title=_duplicated_pages(context, "title"),
        missing_description=sum(
            1 for page in html if not _normalize_text(page.meta_description or "")
        ),
        duplicate_description=_duplicated_pages(context, "description"),
        missing_h1=sum(1 for page in html if not page.h1),
        multiple_h1=sum(1 for page in html if len(page.h1) > 1),
        images_missing_alt=sum(page.images_missing_alt for page in html),
        broken_internal_links=sum(
            1
            for page in context.pages
            if page.status_code is not None
            and page.status_code >= 400
            and context.is_internal(page.url)
        ),
        broken_external_links=sum(1 for check in context.external_checks if check.is_broken),
        missing_canonical=sum(1 for page in indexable if not (page.canonical or "").strip()),
        noindex_pages=sum(1 for page in html if page.is_indexable is False),
        redirect_chains=sum(1 for page in context.pages if page.redirect_chain),
        robots_txt_found=context.crawl.robots_txt_found,
        sitemap_found=context.crawl.sitemap_found,
        sitemap_urls=context.crawl.sitemap_urls,
        structured_data_summary=summarize_structured_data(context),
    )
