"""`robots.txt` y `sitemap.xml`."""

from __future__ import annotations

import pytest
from softree_audit.services.common.http_client import USER_AGENT
from softree_audit.services.crawler.robots import empty_robots, parse_robots, parse_sitemap

pytestmark = pytest.mark.unit

BASE = "https://softree.mx/"

ROBOTS = """
User-agent: *
Disallow: /privado/
Crawl-delay: 2

Sitemap: https://softree.mx/sitemap.xml
Sitemap: /sitemap-noticias.xml
"""


def test_parses_disallow_rules() -> None:
    policy = parse_robots(ROBOTS, BASE)
    assert policy.found is True
    assert policy.allows("https://softree.mx/publico", USER_AGENT) is True
    assert policy.allows("https://softree.mx/privado/x", USER_AGENT) is False


def test_collects_sitemaps_and_resolves_relatives() -> None:
    policy = parse_robots(ROBOTS, BASE)
    assert policy.sitemaps == [
        "https://softree.mx/sitemap.xml",
        "https://softree.mx/sitemap-noticias.xml",
    ]


def test_reads_crawl_delay() -> None:
    assert parse_robots(ROBOTS, BASE).crawl_delay_ms == 2000


def test_without_robots_everything_is_allowed() -> None:
    policy = empty_robots()
    assert policy.found is False
    assert policy.allows("https://softree.mx/lo-que-sea", USER_AGENT) is True


SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://softree.mx/</loc></url>
  <url><loc>https://softree.mx/blog</loc></url>
  <url><loc>ftp://softree.mx/ignorado</loc></url>
</urlset>
"""

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://softree.mx/sitemap-1.xml</loc></sitemap>
  <sitemap><loc>https://softree.mx/sitemap-2.xml</loc></sitemap>
</sitemapindex>
"""


def test_parses_a_sitemap() -> None:
    result = parse_sitemap(SITEMAP.encode(), BASE)
    assert result.is_index is False
    assert result.urls == ["https://softree.mx/", "https://softree.mx/blog"]


def test_parses_a_sitemap_index() -> None:
    result = parse_sitemap(SITEMAP_INDEX.encode(), BASE)
    assert result.is_index is True
    assert len(result.nested_sitemaps) == 2
    assert result.urls == []


def test_unparseable_sitemap_returns_empty_without_raising() -> None:
    assert parse_sitemap(b"esto no es xml", BASE).urls == []


@pytest.mark.security
def test_xxe_entity_is_not_resolved() -> None:
    """Un sitemap es contenido no confiable: sin DTD ni entidades externas."""
    payload = b"""<?xml version="1.0"?>
    <!DOCTYPE urlset [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>&xxe;</loc></url>
    </urlset>
    """
    result = parse_sitemap(payload, BASE)
    assert result.urls == []


@pytest.mark.security
def test_billion_laughs_is_not_expanded() -> None:
    payload = b"""<?xml version="1.0"?>
    <!DOCTYPE lolz [
      <!ENTITY lol "lol">
      <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
      <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
    ]>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>&lol3;</loc></url>
    </urlset>
    """
    result = parse_sitemap(payload, BASE)
    assert result.urls == []
