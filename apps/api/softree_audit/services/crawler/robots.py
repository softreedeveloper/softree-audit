"""`robots.txt` y `sitemap.xml`.

El XML se parsea con `defusedxml`, que deshabilita DTD y entidades externas:
un sitemap es contenido no confiable y sería un vector de XXE y de bomba de
entidades (`docs/spec/security.md` §3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from defusedxml import ElementTree as SafeElementTree

from softree_audit.core.logging import get_logger

logger = get_logger(__name__)

MAX_SITEMAP_URLS = 5000
MAX_SITEMAP_DEPTH = 2  # sitemap index → sitemap → urls


@dataclass(slots=True)
class RobotsPolicy:
    """Directivas de `robots.txt` aplicables al crawler."""

    found: bool = False
    sitemaps: list[str] = field(default_factory=list)
    _parser: RobotFileParser | None = None

    def allows(self, url: str, user_agent: str) -> bool:
        if self._parser is None:
            return True
        return bool(self._parser.can_fetch(user_agent, url))

    @property
    def crawl_delay_ms(self) -> int | None:
        if self._parser is None:
            return None
        delay = self._parser.crawl_delay("*")
        return int(float(delay) * 1000) if delay is not None else None


def parse_robots(content: str, base_url: str) -> RobotsPolicy:
    parser = RobotFileParser()
    parser.parse(content.splitlines())

    sitemaps: list[str] = []
    for line in content.splitlines():
        name, separator, value = line.partition(":")
        if separator and name.strip().lower() == "sitemap":
            candidate = value.strip()
            if candidate:
                sitemaps.append(urljoin(base_url, candidate))

    return RobotsPolicy(found=True, sitemaps=sitemaps, _parser=parser)


def empty_robots() -> RobotsPolicy:
    """Sin `robots.txt` no hay restricciones declaradas."""
    return RobotsPolicy(found=False)


@dataclass(slots=True)
class SitemapResult:
    urls: list[str] = field(default_factory=list)
    nested_sitemaps: list[str] = field(default_factory=list)
    is_index: bool = False


def parse_sitemap(content: bytes, base_url: str) -> SitemapResult:
    """Extrae URLs de un sitemap o los sitemaps de un índice."""
    result = SitemapResult()
    try:
        root = SafeElementTree.fromstring(content)
    except Exception as exc:
        logger.info("sitemap.unparseable", base_url=base_url, error=type(exc).__name__)
        return result

    tag = root.tag.rsplit("}", 1)[-1].lower()
    result.is_index = tag == "sitemapindex"

    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1].lower()
        if name != "loc" or not element.text:
            continue
        location = urljoin(base_url, element.text.strip())
        if urlsplit(location).scheme not in ("http", "https"):
            continue
        if result.is_index:
            result.nested_sitemaps.append(location)
        elif len(result.urls) < MAX_SITEMAP_URLS:
            result.urls.append(location)

    return result
