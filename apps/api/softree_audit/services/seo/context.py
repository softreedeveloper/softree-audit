"""Contexto de evaluación de las reglas SEO.

Las reglas son funciones puras sobre este contexto: sin red, sin base de datos
y sin estado compartido, de modo que cada una se prueba con datos fijos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from softree_audit.services.common.urls import matches_domain
from softree_audit.services.crawler.models import CrawlResult, PageData

# Códigos que consideramos página servida correctamente.
OK_STATUS = range(200, 300)


@dataclass(slots=True)
class ExternalLinkCheck:
    """Resultado de comprobar un enlace externo."""

    url: str
    status_code: int | None
    referrer: str | None
    error: str | None = None

    @property
    def is_broken(self) -> bool:
        return self.status_code is not None and self.status_code >= 400


@dataclass(slots=True)
class SeoContext:
    crawl: CrawlResult
    base_url: str
    allowed_domains: tuple[str, ...]
    external_checks: list[ExternalLinkCheck] = field(default_factory=list)

    @property
    def pages(self) -> list[PageData]:
        return self.crawl.pages

    @property
    def html_pages(self) -> list[PageData]:
        """Páginas HTML servidas correctamente.

        Las reglas de contenido solo tienen sentido sobre estas: exigir un
        title a un 404 o a un PDF sería ruido.
        """
        return [
            page
            for page in self.crawl.pages
            if page.status_code in OK_STATUS
            and page.error is None
            and not page.redirect_chain
            and (page.content_type is None or "html" in page.content_type)
        ]

    @property
    def indexable_pages(self) -> list[PageData]:
        """Páginas que además pueden entrar en el índice."""
        return [page for page in self.html_pages if page.is_indexable is not False]

    def is_internal(self, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return any(matches_domain(host, domain) for domain in self.allowed_domains)
