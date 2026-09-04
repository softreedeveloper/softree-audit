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
from softree_audit.services.reports.model import ReportModel

logger = get_logger(__name__)

TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"
ASSETS_DIR = pathlib.Path(__file__).parent / "assets"

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


def render_html(model: ReportModel) -> str:
    template = _environment().get_template("report.html.j2")
    return template.render(
        model=model,
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


def render_pdf(model: ReportModel) -> bytes:
    from weasyprint import HTML

    html = render_html(model)
    document: bytes = HTML(string=html).write_pdf()
    logger.info("report.pdf_rendered", scan_id=model.scan_id, bytes=len(document))
    return document


def render_json(model: ReportModel) -> bytes:
    return json.dumps(model.as_dict(), ensure_ascii=False, indent=2).encode("utf-8")
