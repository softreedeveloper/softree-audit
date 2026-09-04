"""Traducción de la respuesta de PageSpeed Insights al modelo propio.

La respuesta completa se conserva para trazabilidad; los campos que se
persisten aparte son los que la interfaz y el reporte consultan.
"""

from __future__ import annotations

import decimal
from typing import Any

from softree_audit.core.logging import get_logger
from softree_audit.models.enums import PageSpeedStrategy
from softree_audit.services.performance.models import PageSpeedResult

logger = get_logger(__name__)

# Auditorías de laboratorio de las que se toman las métricas.
LAB_METRICS = {
    "lcp_ms": "largest-contentful-paint",
    "fcp_ms": "first-contentful-paint",
    "tbt_ms": "total-blocking-time",
    "speed_index_ms": "speed-index",
}

CATEGORY_KEYS = {
    "performance_score": "performance",
    "accessibility_score": "accessibility",
    "best_practices_score": "best-practices",
    "seo_score": "seo",
}


def _score_to_percent(raw: Any) -> int | None:
    """Lighthouse devuelve la puntuación de 0 a 1; se presenta de 0 a 100."""
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, round(value * 100)))


def _numeric(audits: dict[str, Any], key: str) -> float | None:
    audit = audits.get(key)
    if not isinstance(audit, dict):
        return None
    value = audit.get("numericValue")
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _field_metric(payload: dict[str, Any], key: str) -> int | None:
    """Percentil de una métrica de campo (CrUX), si el sitio tiene datos."""
    experience = payload.get("loadingExperience")
    if not isinstance(experience, dict):
        return None
    metrics = experience.get("metrics")
    if not isinstance(metrics, dict):
        return None
    metric = metrics.get(key)
    if not isinstance(metric, dict):
        return None
    value = metric.get("percentile")
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def has_field_data(payload: dict[str, Any]) -> bool:
    experience = payload.get("loadingExperience")
    return bool(
        isinstance(experience, dict)
        and isinstance(experience.get("metrics"), dict)
        and experience["metrics"]
    )


def normalize(payload: dict[str, Any], *, url: str, strategy: PageSpeedStrategy) -> PageSpeedResult:
    """Convierte la respuesta de PSI en un `PageSpeedResult`."""
    lighthouse = payload.get("lighthouseResult")
    lighthouse = lighthouse if isinstance(lighthouse, dict) else {}
    categories = lighthouse.get("categories")
    categories = categories if isinstance(categories, dict) else {}
    audits = lighthouse.get("audits")
    audits = audits if isinstance(audits, dict) else {}

    result = PageSpeedResult(
        url=url,
        strategy=strategy,
        lighthouse_version=str(lighthouse.get("lighthouseVersion") or "") or None,
        has_field_data=has_field_data(payload),
        raw=payload,
    )

    for attribute, key in CATEGORY_KEYS.items():
        category = categories.get(key)
        score = _score_to_percent(category.get("score")) if isinstance(category, dict) else None
        setattr(result, attribute, score)

    for attribute, audit_key in LAB_METRICS.items():
        value = _numeric(audits, audit_key)
        setattr(result, attribute, round(value) if value is not None else None)

    cls_value = _numeric(audits, "cumulative-layout-shift")
    if cls_value is not None:
        # CLS no es un tiempo: se guarda con cuatro decimales, sin redondear a entero.
        result.cls = decimal.Decimal(str(round(cls_value, 4)))

    # INP solo llega con datos de campo; el laboratorio no lo mide.
    result.inp_ms = _field_metric(payload, "INTERACTION_TO_NEXT_PAINT")
    if result.inp_ms is None:
        result.inp_ms = _field_metric(payload, "EXPERIMENTAL_INTERACTION_TO_NEXT_PAINT")

    return result
