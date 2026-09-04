"""Extracción de datos de una página (`services/crawler/parser.py`)."""

from __future__ import annotations

import pytest
from softree_audit.services.crawler.parser import extract_page, is_indexable

pytestmark = pytest.mark.unit

DOMAINS = ("softree.mx",)
URL = "https://softree.mx/blog/entrada"

COMPLETE = """
<!doctype html>
<html lang="es">
  <head>
    <title>  Título   de   prueba </title>
    <meta name="description" content="Una descripción de prueba." />
    <meta name="robots" content="index, follow" />
    <link rel="canonical" href="/blog/entrada" />
    <meta property="og:title" content="OG título" />
    <meta name="twitter:card" content="summary" />
    <script type="application/ld+json">
      {"@context": "https://schema.org", "@type": "Article", "headline": "x"}
    </script>
  </head>
  <body>
    <h1>Encabezado principal</h1>
    <h2>Sub uno</h2>
    <h2>Sub dos</h2>
    <a href="/otra">Interna relativa</a>
    <a href="https://softree.mx/tercera">Interna absoluta</a>
    <a href="https://www.softree.mx/sub">Subdominio</a>
    <a href="https://externo.test/x">Externa</a>
    <a href="mailto:hola@softree.mx">Correo</a>
    <a href="tel:+52000">Teléfono</a>
    <a href="javascript:alert(1)">Script</a>
    <a href="#seccion">Ancla</a>
    <img src="/a.png" alt="Con alt" />
    <img src="/b.png" />
    <img src="/c.png" alt="   " />
    <script src="/app.js"></script>
    <form action="/enviar"></form>
  </body>
</html>
"""


def test_extracts_the_head_metadata() -> None:
    page = extract_page(COMPLETE, URL, allowed_domains=DOMAINS)
    assert page.title == "Título de prueba"
    assert page.meta_description == "Una descripción de prueba."
    assert page.meta_robots == "index, follow"
    # El canonical relativo se resuelve contra la URL de la página.
    assert page.canonical == "https://softree.mx/blog/entrada"


def test_extracts_headings() -> None:
    page = extract_page(COMPLETE, URL, allowed_domains=DOMAINS)
    assert page.h1 == ["Encabezado principal"]
    assert page.h2 == ["Sub uno", "Sub dos"]


def test_classifies_internal_and_external_links() -> None:
    page = extract_page(COMPLETE, URL, allowed_domains=DOMAINS)
    assert page.internal_links == 3
    assert page.external_links == 1


def test_ignores_non_navigable_links() -> None:
    """`mailto:`, `tel:`, `javascript:` y anclas no entran en la cola."""
    page = extract_page(COMPLETE, URL, allowed_domains=DOMAINS)
    urls = [link.url for link in page.links]
    assert all(url.startswith("http") for url in urls)
    assert not any("mailto" in url or "javascript" in url for url in urls)
    assert not any(url.endswith("#seccion") for url in urls)


def test_resolves_relative_links() -> None:
    page = extract_page(COMPLETE, URL, allowed_domains=DOMAINS)
    assert "https://softree.mx/otra" in [link.url for link in page.links]


def test_counts_images_without_alt() -> None:
    page = extract_page(COMPLETE, URL, allowed_domains=DOMAINS)
    assert page.images_total == 3
    # Falta el atributo y un alt en blanco cuentan igual.
    assert page.images_missing_alt == 2


def test_counts_scripts_and_forms() -> None:
    page = extract_page(COMPLETE, URL, allowed_domains=DOMAINS)
    assert page.scripts_total == 2  # el JSON-LD también es un <script>
    assert page.forms_total == 1


def test_extracts_structured_data() -> None:
    page = extract_page(COMPLETE, URL, allowed_domains=DOMAINS)
    data = page.structured_data
    assert data["has_json_ld"] is True
    assert data["schema_types"] == ["Article"]
    assert data["open_graph"] == {"og:title": "OG título"}
    assert data["twitter"] == {"twitter:card": "summary"}


def test_invalid_json_ld_is_recorded_without_raising() -> None:
    html = '<html><head><script type="application/ld+json">{no es json}</script></head></html>'
    page = extract_page(html, URL, allowed_domains=DOMAINS)
    assert page.structured_data["json_ld"] == [{"valid": False, "error": "json_invalido"}]


def test_empty_page_yields_empty_fields() -> None:
    page = extract_page("<html><body></body></html>", URL, allowed_domains=DOMAINS)
    assert page.title is None
    assert page.meta_description is None
    assert page.canonical is None
    assert page.h1 == []
    assert page.internal_links == 0


def test_malformed_html_does_not_raise() -> None:
    page = extract_page("<html><body><p>sin cerrar<h1>Título", URL, allowed_domains=DOMAINS)
    assert page.h1 == ["Título"]


@pytest.mark.parametrize(
    ("robots", "expected"),
    [
        (None, True),
        ("index, follow", True),
        ("noindex", False),
        ("NOINDEX, FOLLOW", False),
        ("none", False),
        ("nofollow", True),
    ],
)
def test_indexability(robots: str | None, expected: bool) -> None:
    assert is_indexable(robots) is expected


def test_noindex_page_is_marked_as_not_indexable() -> None:
    html = '<html><head><meta name="robots" content="noindex"></head><body></body></html>'
    page = extract_page(html, URL, allowed_domains=DOMAINS)
    assert page.is_indexable is False
