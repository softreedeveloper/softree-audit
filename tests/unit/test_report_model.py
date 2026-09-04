"""Modelo y renderizado del reporte (ADR-007)."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from softree_audit.services.reports.model import (
    METHODOLOGY_DISCLAIMER,
    SCOPE_DISCLAIMER,
    ReportComparison,
    ReportFinding,
    ReportModel,
    ReportSection,
)
from softree_audit.services.reports.renderer import render_html, render_json

pytestmark = pytest.mark.unit


def finding(**overrides: object) -> ReportFinding:
    defaults: dict[str, object] = {
        "rule_id": "SEO-001",
        "title": "Página sin elemento title",
        "severity": "high",
        "confidence": "high",
        "category": "seo",
        "source": "seo",
        "url": "https://softree.mx/pagina",
        "occurrences": 1,
        "description": "La página no declara un elemento title.",
        "impact": "Reduce la tasa de clic.",
        "remediation": "Añadir un title único.",
        "client_explanation": "Esta página no tiene título.",
        "evidence": None,
        "cwe": None,
        "owasp": None,
    }
    return ReportFinding(**{**defaults, **overrides})  # type: ignore[arg-type]


def model(**overrides: object) -> ReportModel:
    defaults: dict[str, object] = {
        "scan_id": "01a06986-fa23-7357-bd13-60f76491155a",
        "site_name": "Sitio de prueba",
        "site_base_url": "https://softree.mx",
        "project_name": "Proyecto",
        "client_name": "Cliente S.A.",
        "generated_at": dt.datetime(2026, 9, 3, 12, 0, tzinfo=dt.UTC),
        "period_start": dt.datetime(2026, 9, 3, 11, 0, tzinfo=dt.UTC),
        "period_end": dt.datetime(2026, 9, 3, 11, 5, tzinfo=dt.UTC),
        "app_version": "0.1.0",
        "engine_version": "0.1.0",
        "report_version": "v1",
        "softree_overall": 87.1,
        "band": "bueno",
        "softree_categories": {"security": 83.2, "seo": 91.7},
        "applied_weights": {"security": 0.5455, "seo": 0.4545},
        "google_scores": {"performance": 62.0},
        "findings_by_severity": {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 0},
        "pages_crawled": 18,
        "urls_discovered": 18,
    }
    return ReportModel(**{**defaults, **overrides})  # type: ignore[arg-type]


# ── Modelo ─────────────────────────────────────────────────────────────────


def test_total_findings_sums_every_severity() -> None:
    assert model().total_findings == 6


def test_serialization_is_json_compatible() -> None:
    payload = json.loads(json.dumps(model().as_dict()))
    assert payload["scan_id"]
    assert payload["generated_at"].startswith("2026-09-03")
    assert payload["total_findings"] == 6


def test_the_disclaimers_are_part_of_the_model() -> None:
    """El aviso de metodología es obligatorio (`reports.md` §5)."""
    data = model().as_dict()
    assert "no constituye una calificación oficial de Google" in data["methodology_disclaimer"]
    assert "pasivo" in data["scope_disclaimer"]
    assert METHODOLOGY_DISCLAIMER and SCOPE_DISCLAIMER


# ── HTML ───────────────────────────────────────────────────────────────────


def test_html_includes_the_cover_data() -> None:
    html = render_html(model())
    assert "SOFTREE" in html
    assert "Cliente S.A." in html
    assert "https://softree.mx" in html
    assert "Softree Audit 0.1.0" in html


def test_html_shows_both_score_systems_labelled() -> None:
    """§27: el score propio nunca se presenta como oficial de Google."""
    html = render_html(model())
    assert "Softree Score" in html
    assert "Google Lighthouse" in html
    assert "no constituye una calificación oficial de Google" in html


def test_html_includes_the_two_reading_levels() -> None:
    """§34: detalle técnico y explicación para el cliente."""
    html = render_html(
        model(
            sections=[
                ReportSection(
                    key="seo", title="SEO", module_status="completed", findings=[finding()]
                )
            ]
        )
    )
    assert "En términos claros" in html
    assert "Esta página no tiene título." in html
    assert "La página no declara un elemento title." in html
    assert "Cómo se corrige" in html


def test_a_module_that_did_not_run_is_declared_in_the_report() -> None:
    """No decirlo haría creer que la sección está limpia."""
    html = render_html(
        model(
            sections=[
                ReportSection(
                    key="performance",
                    title="Rendimiento",
                    module_status="skipped",
                    note=(
                        "Este módulo no se ejecutó. La ausencia de hallazgos no significa "
                        "que no existan problemas."
                    ),
                )
            ]
        )
    )
    assert "no se ejecutó" in html
    assert "no significa que no existan problemas" in html


def test_html_escapes_content_coming_from_the_audited_site() -> None:
    """El contenido del target es no confiable y no debe inyectar marcado."""
    html = render_html(
        model(
            sections=[
                ReportSection(
                    key="seo",
                    title="SEO",
                    module_status="completed",
                    findings=[
                        finding(title="<script>alert(1)</script>", evidence="<img onerror=x>")
                    ],
                )
            ]
        )
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_html_includes_the_comparison_when_there_is_one() -> None:
    html = render_html(
        model(
            comparison=ReportComparison(
                previous_scan_id="anterior",
                previous_finished_at=dt.datetime(2026, 9, 1, tzinfo=dt.UTC),
                counts={"new": 1, "fixed": 2, "unchanged": 3, "regressed": 0},
                metrics=[
                    {
                        "key": "softree_overall",
                        "label": "Softree Score",
                        "previous": 80.0,
                        "current": 87.1,
                        "delta": 7.1,
                        "direction": "mejora",
                        "unit": "",
                        "higher_is_better": True,
                    }
                ],
                compared_sources=["seo"],
                sources_only_in_previous=["zap"],
            )
        )
    )
    assert "Comparación con la auditoría anterior" in html
    assert "Softree Score" in html
    # Se declara lo que no pudo compararse. La plantilla parte la frase en
    # varias líneas, así que se compara sobre el texto normalizado.
    flat = " ".join(html.split())
    assert "No se comparan zap" in flat
    assert "no cuentan como corregidos" in flat


def test_a_first_audit_has_no_comparison_section() -> None:
    assert "Comparación con la auditoría anterior" not in render_html(model())


def test_summary_labels_are_in_spanish() -> None:
    html = render_html(
        model(
            sections=[
                ReportSection(
                    key="seo",
                    title="SEO",
                    module_status="completed",
                    summary={"pages_crawled": 18, "robots_txt_found": True},
                )
            ]
        )
    )
    assert "Páginas rastreadas" in html
    assert "robots.txt encontrado" in html
    assert "Pages crawled" not in html


# ── JSON ───────────────────────────────────────────────────────────────────


def test_json_and_html_come_from_the_same_model() -> None:
    """ADR-007: los formatos no pueden divergir en contenido."""
    source = model(
        sections=[
            ReportSection(key="seo", title="SEO", module_status="completed", findings=[finding()])
        ]
    )
    payload = json.loads(render_json(source))
    html = render_html(source)

    assert payload["softree_overall"] == 87.1
    assert "87.1" in html
    assert payload["sections"][0]["findings"][0]["title"] == "Página sin elemento title"
    assert "Página sin elemento title" in html


def test_json_is_valid_utf8() -> None:
    payload = render_json(model(site_name="Sitio con acentós y ñ"))
    assert "acentós" in json.loads(payload)["site_name"]


def test_the_stylesheet_is_not_html_escaped() -> None:
    """Con autoescape, las comillas de `font-family` romperían el CSS.

    WeasyPrint descarta la regla entera y el PDF pierde tipografía y estilos.
    """
    html = render_html(model())
    assert '"DejaVu Sans"' in html
    assert "&#34;DejaVu Sans&#34;" not in html
    assert "&amp;" not in html.split("</style>")[0]


def test_the_pdf_renders_without_css_errors(capsys: pytest.CaptureFixture[str]) -> None:
    """WeasyPrint avisa por stderr de cada regla que no puede interpretar."""
    import logging

    from softree_audit.services.reports.renderer import render_pdf

    records: list[logging.LogRecord] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("weasyprint")
    handler = Collector()
    logger.addHandler(handler)
    try:
        document = render_pdf(model())
    finally:
        logger.removeHandler(handler)

    assert document.startswith(b"%PDF-")
    problems = [record.getMessage() for record in records if record.levelno >= logging.WARNING]
    assert problems == [], problems
