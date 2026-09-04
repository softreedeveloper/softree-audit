"""Agregados SEO y resumen de datos estructurados."""

from __future__ import annotations

import pytest
from softree_audit.services.crawler.models import CrawlResult, PageData
from softree_audit.services.seo.aggregates import build_aggregates, summarize_structured_data
from softree_audit.services.seo.context import ExternalLinkCheck, SeoContext

pytestmark = pytest.mark.unit

DOMAIN = "softree.mx"
BASE = f"https://{DOMAIN}"


def page(path: str, **overrides: object) -> PageData:
    defaults: dict[str, object] = {
        "url": f"{BASE}{path}",
        "depth": 0,
        "status_code": 200,
        "content_type": "text/html",
        "title": f"Título {path}",
        "meta_description": f"Descripción {path}",
        "canonical": f"{BASE}{path}",
        "h1": ["Encabezado"],
        "is_indexable": True,
    }
    return PageData(**{**defaults, **overrides})  # type: ignore[arg-type]


def context(pages: list[PageData], **crawl: object) -> SeoContext:
    defaults: dict[str, object] = {
        "pages": pages,
        "urls_discovered": len(pages),
        "robots_txt_found": True,
        "sitemap_found": True,
        "sitemap_urls": 3,
    }
    return SeoContext(
        crawl=CrawlResult(**{**defaults, **crawl}),  # type: ignore[arg-type]
        base_url=BASE,
        allowed_domains=(DOMAIN,),
    )


def test_counts_every_indicator() -> None:
    pages = [
        page("/a", title=None),
        page("/b", meta_description=None),
        page("/c", h1=[]),
        page("/d", h1=["uno", "dos"]),
        page("/e", images_total=3, images_missing_alt=2),
        page("/f", canonical=None),
        page("/g", is_indexable=False),
        page("/rota", status_code=404),
        page("/redirige", redirect_chain=[{"from": "x", "to": "y", "status": 301}]),
    ]
    aggregates = build_aggregates(context(pages))

    assert aggregates.pages_crawled == 9
    assert aggregates.missing_title == 1
    assert aggregates.missing_description == 1
    assert aggregates.missing_h1 == 1
    assert aggregates.multiple_h1 == 1
    assert aggregates.images_missing_alt == 2
    assert aggregates.missing_canonical == 1
    assert aggregates.noindex_pages == 1
    assert aggregates.broken_internal_links == 1
    assert aggregates.redirect_chains == 1
    assert aggregates.robots_txt_found is True
    assert aggregates.sitemap_found is True
    assert aggregates.sitemap_urls == 3


def test_counts_pages_involved_in_duplicates() -> None:
    pages = [
        page("/a", title="Igual", meta_description="Igual"),
        page("/b", title="Igual", meta_description="Igual"),
        page("/c", title="Igual", meta_description="Distinta"),
        page("/d"),
    ]
    aggregates = build_aggregates(context(pages))
    assert aggregates.duplicate_title == 3
    assert aggregates.duplicate_description == 2


def test_external_links_are_counted_only_when_checked() -> None:
    ctx = context([page("/")])
    assert build_aggregates(ctx).broken_external_links == 0

    ctx.external_checks = [
        ExternalLinkCheck(url="https://x.test/1", status_code=404, referrer=None),
        ExternalLinkCheck(url="https://x.test/2", status_code=200, referrer=None),
    ]
    assert build_aggregates(ctx).broken_external_links == 1


def test_aggregates_serialize_to_the_database_shape() -> None:
    data = build_aggregates(context([page("/")])).as_dict()
    assert "structured_data_summary" in data
    assert isinstance(data["structured_data_summary"], dict)


def test_structured_data_summary() -> None:
    pages = [
        page(
            "/a",
            structured_data={
                "has_json_ld": True,
                "has_open_graph": True,
                "has_twitter": False,
                "json_ld": [{"valid": True, "type": "Article"}],
                "schema_types": ["Article"],
            },
        ),
        page(
            "/b",
            structured_data={
                "has_json_ld": True,
                "has_open_graph": False,
                "has_twitter": True,
                "json_ld": [{"valid": False, "error": "json_invalido"}],
                "schema_types": [],
            },
        ),
        page("/c", structured_data={}),
    ]
    summary = summarize_structured_data(context(pages))

    assert summary["pages_analyzed"] == 3
    assert summary["pages_with_json_ld"] == 2
    assert summary["pages_with_open_graph"] == 1
    assert summary["pages_with_twitter_cards"] == 1
    assert summary["invalid_json_ld_blocks"] == 1
    assert summary["schema_types"] == ["Article"]


def test_empty_crawl_produces_zeroed_aggregates() -> None:
    aggregates = build_aggregates(context([]))
    assert aggregates.pages_crawled == 0
    assert aggregates.missing_title == 0
