"""Reglas SEO-001 a SEO-016.

Cada regla se prueba con páginas construidas a mano: sin red, sin base de datos
y sin depender del crawler.
"""

from __future__ import annotations

import pytest
from softree_audit.models.enums import FindingCategory, Severity
from softree_audit.services.crawler.models import CrawlResult, Link, PageData
from softree_audit.services.seo import rules
from softree_audit.services.seo.context import ExternalLinkCheck, SeoContext
from softree_audit.services.seo.engine import analyze

pytestmark = pytest.mark.unit

DOMAIN = "softree.mx"
BASE = f"https://{DOMAIN}"


def page(path: str = "/", **overrides: object) -> PageData:
    defaults: dict[str, object] = {
        "url": f"{BASE}{path}",
        "depth": 0,
        "status_code": 200,
        "content_type": "text/html",
        "title": "Título correcto",
        "meta_description": "Descripción correcta de la página.",
        "canonical": f"{BASE}{path}",
        "h1": ["Encabezado"],
        "is_indexable": True,
    }
    return PageData(**{**defaults, **overrides})  # type: ignore[arg-type]


def context(
    pages: list[PageData],
    *,
    robots: bool = True,
    sitemap: bool = True,
    external: list[ExternalLinkCheck] | None = None,
) -> SeoContext:
    crawl = CrawlResult(
        pages=pages,
        urls_discovered=len(pages),
        robots_txt_found=robots,
        sitemap_found=sitemap,
        sitemap_urls=len(pages) if sitemap else 0,
    )
    return SeoContext(
        crawl=crawl,
        base_url=BASE,
        allowed_domains=(DOMAIN,),
        external_checks=external or [],
    )


# ── SEO-001 / SEO-003 / SEO-005 / SEO-006 ──────────────────────────────────


def test_seo_001_missing_title() -> None:
    findings = rules.missing_title(context([page("/a", title=None), page("/b")]))
    assert [f.url for f in findings] == [f"{BASE}/a"]
    assert findings[0].rule_id == "SEO-001"
    assert findings[0].severity is Severity.HIGH


def test_seo_001_treats_whitespace_as_missing() -> None:
    assert len(rules.missing_title(context([page("/a", title="   ")]))) == 1


def test_seo_001_ignores_non_html_and_error_pages() -> None:
    """Exigir un title a un 404 o a un PDF sería ruido."""
    pages = [
        page("/error", status_code=404, title=None),
        page("/doc.pdf", content_type="application/pdf", title=None),
        page("/redirige", title=None, redirect_chain=[{"from": "x", "to": "y", "status": 301}]),
    ]
    assert rules.missing_title(context(pages)) == []


def test_seo_003_missing_description() -> None:
    findings = rules.missing_description(context([page("/a", meta_description=None), page("/b")]))
    assert [f.url for f in findings] == [f"{BASE}/a"]


def test_seo_005_missing_h1() -> None:
    findings = rules.missing_h1(context([page("/a", h1=[]), page("/b")]))
    assert [f.url for f in findings] == [f"{BASE}/a"]


def test_seo_006_multiple_h1() -> None:
    findings = rules.multiple_h1(context([page("/a", h1=["uno", "dos", "tres"]), page("/b")]))
    assert len(findings) == 1
    assert findings[0].occurrences == 3


def test_seo_006_ignores_a_single_h1() -> None:
    assert rules.multiple_h1(context([page("/a", h1=["uno"])])) == []


# ── SEO-002 / SEO-004 / SEO-016 ────────────────────────────────────────────


def test_seo_002_duplicate_titles_produce_one_finding_per_group() -> None:
    pages = [
        page("/a", title="Repetido"),
        page("/b", title="Repetido"),
        page("/c", title="Único"),
    ]
    findings = rules.duplicate_titles(context(pages))
    assert len(findings) == 1
    assert findings[0].occurrences == 2
    assert f"{BASE}/a" in (findings[0].evidence or "")
    assert f"{BASE}/b" in (findings[0].evidence or "")


def test_seo_002_comparison_ignores_case_and_whitespace() -> None:
    pages = [page("/a", title="  Mismo  Título "), page("/b", title="mismo título")]
    assert len(rules.duplicate_titles(context(pages))) == 1


def test_seo_002_ignores_pages_without_title() -> None:
    pages = [page("/a", title=None), page("/b", title=None)]
    assert rules.duplicate_titles(context(pages)) == []


def test_seo_004_duplicate_descriptions() -> None:
    pages = [
        page("/a", meta_description="Igual"),
        page("/b", meta_description="Igual"),
        page("/c", meta_description="Distinta"),
    ]
    findings = rules.duplicate_descriptions(context(pages))
    assert len(findings) == 1
    assert findings[0].occurrences == 2


def test_seo_016_requires_title_description_and_h1_to_match() -> None:
    """Señal más fuerte que un simple title repetido."""
    duplicated = [
        page("/a", title="T", meta_description="D", h1=["H"]),
        page("/b", title="T", meta_description="D", h1=["H"]),
    ]
    assert len(rules.duplicate_content(context(duplicated))) == 1

    only_title = [
        page("/a", title="T", meta_description="D1", h1=["H1"]),
        page("/b", title="T", meta_description="D2", h1=["H2"]),
    ]
    assert rules.duplicate_content(context(only_title)) == []


# ── SEO-007 ────────────────────────────────────────────────────────────────


def test_seo_007_missing_alt_counts_images() -> None:
    findings = rules.missing_alt(
        context([page("/a", images_total=5, images_missing_alt=2), page("/b")])
    )
    assert len(findings) == 1
    assert findings[0].occurrences == 2
    assert findings[0].category is FindingCategory.ACCESSIBILITY


# ── SEO-008 / SEO-009 ──────────────────────────────────────────────────────


def test_seo_008_broken_internal_link_reports_the_origin() -> None:
    broken = page("/rota", status_code=404, discovered_from=f"{BASE}/origen")
    findings = rules.broken_internal_links(context([page("/"), broken]))
    assert len(findings) == 1
    assert findings[0].url == f"{BASE}/rota"
    assert f"{BASE}/origen" in (findings[0].evidence or "")
    assert findings[0].severity is Severity.HIGH


def test_seo_008_ignores_successful_pages() -> None:
    assert rules.broken_internal_links(context([page("/"), page("/b")])) == []


def test_seo_009_without_checks_is_silent() -> None:
    """Sin la comprobación habilitada no hay datos: la regla calla."""
    pages = [page("/", links=[Link(url="https://externo.test/x", text="x", is_internal=False)])]
    assert rules.broken_external_links(context(pages)) == []


def test_seo_009_reports_broken_external_links() -> None:
    checks = [
        ExternalLinkCheck(url="https://externo.test/roto", status_code=404, referrer=f"{BASE}/"),
        ExternalLinkCheck(url="https://externo.test/ok", status_code=200, referrer=f"{BASE}/"),
        # Un fallo de red no es un enlace roto comprobado.
        ExternalLinkCheck(
            url="https://externo.test/timeout", status_code=None, referrer=None, error="Timeout"
        ),
    ]
    findings = rules.broken_external_links(context([page("/")], external=checks))
    assert [f.url for f in findings] == ["https://externo.test/roto"]


# ── SEO-010 / SEO-011 ──────────────────────────────────────────────────────


def test_seo_010_missing_canonical() -> None:
    findings = rules.missing_canonical(context([page("/a", canonical=None), page("/b")]))
    assert [f.url for f in findings] == [f"{BASE}/a"]


def test_seo_011_canonical_to_another_domain() -> None:
    findings = rules.invalid_canonical(
        context([page("/a", canonical="https://otro-dominio.test/x")])
    )
    assert len(findings) == 1
    assert "dominio ajeno" in (findings[0].evidence or "")


def test_seo_011_canonical_that_is_not_a_url() -> None:
    findings = rules.invalid_canonical(context([page("/a", canonical="no-es-una-url")]))
    assert len(findings) == 1


def test_seo_011_canonical_pointing_to_an_error_page() -> None:
    pages = [page("/a", canonical=f"{BASE}/rota"), page("/rota", status_code=404)]
    findings = rules.invalid_canonical(context(pages))
    assert len(findings) == 1
    assert "responde 404" in (findings[0].evidence or "")


def test_seo_011_accepts_a_valid_canonical() -> None:
    assert rules.invalid_canonical(context([page("/a")])) == []


def test_seo_011_accepts_a_canonical_to_a_subdomain() -> None:
    findings = rules.invalid_canonical(context([page("/a", canonical=f"https://www.{DOMAIN}/a")]))
    assert findings == []


# ── SEO-012 ────────────────────────────────────────────────────────────────


def test_seo_012_noindex() -> None:
    noindex = page("/a", is_indexable=False, meta_robots="noindex, follow")
    findings = rules.noindex_pages(context([noindex, page("/b")]))
    assert len(findings) == 1
    assert "noindex" in (findings[0].evidence or "")


def test_noindex_pages_are_excluded_from_duplicate_analysis() -> None:
    """Una página fuera del índice no compite por las mismas búsquedas."""
    pages = [
        page("/a", title="Repetido"),
        page("/b", title="Repetido", is_indexable=False),
    ]
    assert rules.duplicate_titles(context(pages)) == []


# ── SEO-013 / SEO-014 ──────────────────────────────────────────────────────


def test_seo_013_sitemap_missing() -> None:
    assert len(rules.sitemap_missing(context([page("/")], sitemap=False))) == 1
    assert rules.sitemap_missing(context([page("/")], sitemap=True)) == []


def test_seo_014_robots_missing() -> None:
    assert len(rules.robots_missing(context([page("/")], robots=False))) == 1
    assert rules.robots_missing(context([page("/")], robots=True)) == []


# ── SEO-015 ────────────────────────────────────────────────────────────────


def test_seo_015_single_redirect_is_informative() -> None:
    redirected = page(
        "/vieja",
        status_code=301,
        redirect_chain=[{"from": f"{BASE}/vieja", "to": f"{BASE}/nueva", "status": 301}],
    )
    findings = rules.redirect_chains(context([redirected]))
    assert len(findings) == 1
    assert findings[0].severity is Severity.INFO


def test_seo_015_chain_of_two_or_more_is_a_low_severity_issue() -> None:
    redirected = page(
        "/uno",
        status_code=302,
        redirect_chain=[
            {"from": f"{BASE}/uno", "to": f"{BASE}/dos", "status": 302},
            {"from": f"{BASE}/dos", "to": f"{BASE}/tres", "status": 302},
        ],
    )
    findings = rules.redirect_chains(context([redirected]))
    assert findings[0].severity is Severity.LOW
    assert findings[0].occurrences == 2
    assert "/tres" in (findings[0].evidence or "")


# ── Motor completo ─────────────────────────────────────────────────────────


def test_engine_runs_every_rule() -> None:
    analysis = analyze(context([page("/")]))
    assert analysis.rules_evaluated == 16
    assert analysis.rules_failed == []


def test_engine_deduplicates_findings() -> None:
    """Una misma página con dos carencias produce dos hallazgos distintos."""
    analysis = analyze(context([page("/a", title=None, meta_description=None)]))
    fingerprints = [finding.fingerprint for finding in analysis.findings]
    assert len(fingerprints) == len(set(fingerprints))


def test_engine_on_a_clean_site_reports_nothing() -> None:
    analysis = analyze(context([page("/"), page("/b", title="Otro", meta_description="Otra")]))
    assert analysis.findings == []


def test_engine_survives_a_failing_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Una regla rota no debe invalidar el análisis completo."""

    def explode(_context: SeoContext) -> list[object]:
        raise RuntimeError("regla rota")

    monkeypatch.setitem(rules.RULES, "SEO-001", explode)  # type: ignore[arg-type]
    analysis = analyze(context([page("/a", title=None, h1=[])]))

    assert analysis.rules_failed == ["SEO-001"]
    assert analysis.rules_evaluated == 15
    # El resto de reglas sí produjo resultados.
    assert any(finding.rule_id == "SEO-005" for finding in analysis.findings)
