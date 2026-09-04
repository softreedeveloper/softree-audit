"""Extracción de datos de una página HTML.

Solo lectura y análisis: no emite peticiones ni toca la base de datos, por lo
que se puede probar con HTML fijo y sin red.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin, urlsplit

from selectolax.parser import HTMLParser

from softree_audit.services.common.urls import matches_domain
from softree_audit.services.crawler.models import Link, PageData

# Esquemas que no son navegables y no deben entrar en la cola.
NON_NAVIGABLE_SCHEMES = frozenset({"mailto", "tel", "javascript", "data", "sms", "ftp", "file"})

MAX_TEXT = 2000
MAX_HEADINGS = 50
MAX_LINKS = 500


def _clean(value: str | None, limit: int = MAX_TEXT) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    if not text:
        return None
    return text[:limit]


def extract_page(html: str, url: str, *, allowed_domains: tuple[str, ...]) -> PageData:
    """Analiza el HTML de una página ya descargada."""
    tree = HTMLParser(html)
    page = PageData(url=url, depth=0)

    title_node = tree.css_first("title")
    page.title = _clean(title_node.text() if title_node else None, 512)

    for node in tree.css("meta"):
        name = (node.attributes.get("name") or "").lower()
        if name == "description":
            page.meta_description = _clean(node.attributes.get("content"), 1024)
        elif name == "robots":
            page.meta_robots = _clean(node.attributes.get("content"), 256)

    canonical = tree.css_first('link[rel="canonical"]')
    if canonical is not None:
        href = canonical.attributes.get("href")
        page.canonical = _clean(urljoin(url, href) if href else None, 2048)

    page.h1 = [text for node in tree.css("h1")[:MAX_HEADINGS] if (text := _clean(node.text(), 512))]
    page.h2 = [text for node in tree.css("h2")[:MAX_HEADINGS] if (text := _clean(node.text(), 512))]

    page.links = _extract_links(tree, url, allowed_domains)
    page.internal_links = sum(1 for link in page.links if link.is_internal)
    page.external_links = sum(1 for link in page.links if not link.is_internal)

    images = tree.css("img")
    page.images_total = len(images)
    page.images_missing_alt = sum(
        1 for node in images if not (node.attributes.get("alt") or "").strip()
    )

    page.scripts_total = len(tree.css("script"))
    page.forms_total = len(tree.css("form"))
    page.structured_data = extract_structured_data(tree)
    page.is_indexable = is_indexable(page.meta_robots)
    return page


def is_indexable(meta_robots: str | None) -> bool:
    """`noindex` en la meta robots excluye la página del índice."""
    if not meta_robots:
        return True
    directives = {part.strip().lower() for part in meta_robots.split(",")}
    return "noindex" not in directives and "none" not in directives


def _extract_links(tree: HTMLParser, base_url: str, allowed_domains: tuple[str, ...]) -> list[Link]:
    links: list[Link] = []
    seen: set[str] = set()

    for node in tree.css("a[href]"):
        href = (node.attributes.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue

        scheme = urlsplit(href).scheme.lower()
        if scheme in NON_NAVIGABLE_SCHEMES:
            continue

        absolute = urljoin(base_url, href)
        absolute = urlsplit(absolute)._replace(fragment="").geturl()
        if absolute in seen:
            continue
        seen.add(absolute)

        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https"):
            continue

        host = (parts.hostname or "").lower()
        internal = any(matches_domain(host, domain) for domain in allowed_domains)
        links.append(
            Link(
                url=absolute,
                text=_clean(node.text(), 200) or "",
                rel=_clean(node.attributes.get("rel"), 100),
                is_internal=internal,
            )
        )
        if len(links) >= MAX_LINKS:
            break

    return links


def extract_structured_data(tree: HTMLParser) -> dict[str, Any]:
    """Presencia y estructura básica de datos estructurados (§20).

    En el MVP se registra qué hay; la validación profunda queda para más
    adelante.
    """
    json_ld: list[dict[str, Any]] = []
    types: list[str] = []

    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text() or ""
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            json_ld.append({"valid": False, "error": "json_invalido"})
            continue

        entries = parsed if isinstance(parsed, list) else [parsed]
        for entry in entries:
            if not isinstance(entry, dict):
                json_ld.append({"valid": False, "error": "estructura_inesperada"})
                continue
            schema_type = entry.get("@type")
            if isinstance(schema_type, list):
                types.extend(str(item) for item in schema_type)
            elif schema_type is not None:
                types.append(str(schema_type))
            json_ld.append({"valid": True, "type": schema_type, "has_context": "@context" in entry})

    open_graph: dict[str, str] = {}
    twitter: dict[str, str] = {}
    for node in tree.css("meta"):
        prop = (node.attributes.get("property") or "").lower()
        name = (node.attributes.get("name") or "").lower()
        content = _clean(node.attributes.get("content"), 512)
        if not content:
            continue
        if prop.startswith("og:"):
            open_graph[prop] = content
        elif name.startswith("twitter:"):
            twitter[name] = content

    return {
        "json_ld": json_ld,
        "schema_types": sorted(set(types)),
        "open_graph": open_graph,
        "twitter": twitter,
        "has_json_ld": bool(json_ld),
        "has_open_graph": bool(open_graph),
        "has_twitter": bool(twitter),
    }
