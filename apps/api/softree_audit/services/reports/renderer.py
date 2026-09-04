"""Renderizado del reporte en HTML, PDF y JSON.

Los tres formatos salen del mismo `ReportModel` (ADR-007). WeasyPrint no ejecuta
JavaScript: el PDF se compone solo con HTML y CSS.
"""

from __future__ import annotations

import base64
import json
import pathlib
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from softree_audit.core.logging import get_logger
from softree_audit.models.enums import ReportAudience
from softree_audit.services.reports.model import ReportModel

logger = get_logger(__name__)

TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"
ASSETS_DIR = pathlib.Path(__file__).parent / "assets"

AUDIENCES = {
    ReportAudience.EXECUTIVE: "Versión ejecutiva",
    ReportAudience.TECHNICAL: "Versión técnica",
    ReportAudience.COMBINED: "Versión completa",
}

BANDS = {
    "excelente": "Excelente",
    "bueno": "Bueno",
    "mejorable": "Mejorable",
    "deficiente": "Deficiente",
    "critico": "Crítico",
}

CATEGORIES = {
    "overall": "Global",
    "security": "Seguridad",
    "performance": "Rendimiento",
    "seo": "SEO",
    "accessibility": "Accesibilidad",
    "best_practices": "Buenas prácticas",
}

SEVERITIES = {
    "critical": "Crítica",
    "high": "Alta",
    "medium": "Media",
    "low": "Baja",
    "info": "Informativa",
}

MODULES = {
    "discovery": "Descubrimiento",
    "crawler": "Rastreo",
    "security": "Seguridad (OWASP ZAP)",
    "seo": "SEO",
    "performance": "Rendimiento (PageSpeed Insights)",
    "search_console": "Search Console",
    "findings": "Hallazgos",
    "scoring": "Puntuación",
    "report": "Reporte",
}

SUMMARY_LABELS = {
    "pages_crawled": "Páginas rastreadas",
    "urls_discovered": "URL descubiertas",
    "missing_title": "Páginas sin title",
    "duplicate_title": "Páginas con title duplicado",
    "missing_description": "Páginas sin meta description",
    "missing_h1": "Páginas sin H1",
    "images_missing_alt": "Imágenes sin texto alternativo",
    "broken_internal_links": "Enlaces internos rotos",
    "robots_txt_found": "robots.txt encontrado",
    "sitemap_found": "sitemap.xml encontrado",
    "urls_analyzed": "URL analizadas",
    "alerts_received": "Alertas recibidas de ZAP",
    "active_scan": "Análisis activo",
    "property_url": "Propiedad de Search Console",
    "totals": "Totales",
    "score": "Softree Score de la categoría",
    "google_score": "Puntuación de Google",
    "mobile": "Móvil",
    "desktop": "Escritorio",
    "performance": "Rendimiento",
    "accessibility": "Accesibilidad",
    "best_practices": "Buenas prácticas",
    "seo": "SEO",
    "lcp_ms": "LCP (ms)",
    "cls": "CLS",
    "inp_ms": "INP (ms)",
    "tbt_ms": "TBT (ms)",
    "has_field_data": "Con datos de campo",
}


def _summary_label(key: str) -> str:
    return SUMMARY_LABELS.get(key, key.replace("_", " ").capitalize())


STATUSES = {
    "completed": "completado",
    "failed": "falló",
    "skipped": "omitido",
    "pending": "pendiente",
    "running": "en ejecución",
}


def _render_value(value: Any) -> str:
    """Formatea un valor del resumen para la plantilla."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if isinstance(value, dict):
        return ", ".join(f"{key}: {_render_value(item)}" for key, item in value.items())
    if isinstance(value, list):
        return ", ".join(_render_value(item) for item in value) or "—"
    return str(value)


def _logo_data_uri() -> str | None:
    """Logo embebido como data URI.

    WeasyPrint resolvería una ruta de archivo, pero embeberlo hace que el HTML
    sea autocontenido y se pueda entregar como un único archivo.
    """
    logo = ASSETS_DIR / "softree-isotipo.png"
    if not logo.exists():
        return None
    encoded = base64.b64encode(logo.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html", "xml", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html(model: ReportModel, audience: ReportAudience = ReportAudience.COMBINED) -> str:
    """Compone el documento para una audiencia.

    La audiencia decide qué se muestra, no qué se mide: los tres documentos
    salen del mismo `ReportModel` y describen la misma auditoría.

    - `executive`: puntuaciones, hallazgos destacados en lenguaje de cliente y
      recomendaciones. Sin evidencia ni detalle por módulo.
    - `technical`: el detalle completo con evidencia, CWE y OWASP, sin las
      paráfrasis dirigidas al cliente.
    - `combined`: todo.
    """
    template = _environment().get_template("report.html.j2")
    return template.render(
        model=model,
        audience=audience.value,
        audience_label=AUDIENCES[audience],
        client_language=audience in (ReportAudience.EXECUTIVE, ReportAudience.COMBINED),
        technical_detail=audience in (ReportAudience.TECHNICAL, ReportAudience.COMBINED),
        highlighted_findings=highlighted_findings(model),
        css=(TEMPLATES_DIR / "report.css").read_text(encoding="utf-8"),
        logo=_logo_data_uri(),
        bands=BANDS,
        categories=CATEGORIES,
        severities=SEVERITIES,
        modules=MODULES,
        statuses=STATUSES,
        render_value=_render_value,
        summary_label=_summary_label,
    )


def render_pdf(model: ReportModel, audience: ReportAudience = ReportAudience.COMBINED) -> bytes:
    from weasyprint import HTML

    html = render_html(model, audience)
    document: bytes = HTML(string=html).write_pdf()
    logger.info(
        "report.pdf_rendered",
        scan_id=model.scan_id,
        audience=audience.value,
        bytes=len(document),
    )
    return document


def render_json(model: ReportModel, audience: ReportAudience = ReportAudience.COMBINED) -> bytes:
    """El JSON lleva siempre el modelo completo.

    Es el formato de integración: recortarlo por audiencia rompería a quien lo
    consume. La audiencia se anota para que el consumidor sepa con qué
    intención se generó.
    """
    data = model.as_dict()
    data["audience"] = audience.value
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


# Gravedades que llegan al resumen para dirección.
HIGHLIGHTED_SEVERITIES = ("critical", "high")


def highlighted_findings(model: ReportModel) -> list[Any]:
    """Hallazgos que el documento ejecutivo enumera, en orden de gravedad.

    Si no hay ninguno crítico ni alto, se recurre a las recomendaciones ya
    priorizadas para no entregar un documento sin contenido accionable.
    """
    urgent = [
        finding
        for section in model.sections
        for finding in section.findings
        if finding.severity in HIGHLIGHTED_SEVERITIES
    ]
    if urgent:
        return sorted(urgent, key=lambda item: HIGHLIGHTED_SEVERITIES.index(item.severity))
    return list(model.recommendations)
