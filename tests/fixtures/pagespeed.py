"""Respuestas de ejemplo de PageSpeed Insights.

Reproducen la forma documentada de la API v5. Solo se usan en pruebas: en
producción la integración habla con la API real (§52).
"""

from __future__ import annotations

from typing import Any


def response(
    *,
    performance: float | None = 0.87,
    accessibility: float | None = 0.92,
    best_practices: float | None = 0.96,
    seo: float | None = 1.0,
    lcp_ms: float | None = 2450.5,
    cls: float | None = 0.043,
    fcp_ms: float | None = 1200.1,
    tbt_ms: float | None = 150.0,
    speed_index_ms: float | None = 3300.0,
    inp_ms: int | None = None,
    lighthouse_version: str = "12.2.1",
    url: str = "https://softree.mx/",
) -> dict[str, Any]:
    audits: dict[str, Any] = {}
    for key, value, display in (
        ("largest-contentful-paint", lcp_ms, "2.5 s"),
        ("cumulative-layout-shift", cls, "0.043"),
        ("first-contentful-paint", fcp_ms, "1.2 s"),
        ("total-blocking-time", tbt_ms, "150 ms"),
        ("speed-index", speed_index_ms, "3.3 s"),
    ):
        if value is not None:
            audits[key] = {"numericValue": value, "displayValue": display, "score": 0.8}

    categories: dict[str, Any] = {}
    for key, value in (
        ("performance", performance),
        ("accessibility", accessibility),
        ("best-practices", best_practices),
        ("seo", seo),
    ):
        if value is not None:
            categories[key] = {"id": key, "score": value}

    payload: dict[str, Any] = {
        "id": url,
        "lighthouseResult": {
            "requestedUrl": url,
            "finalUrl": url,
            "lighthouseVersion": lighthouse_version,
            "categories": categories,
            "audits": audits,
        },
        "analysisUTCTimestamp": "2026-09-03T20:00:00.000Z",
    }

    if inp_ms is not None:
        payload["loadingExperience"] = {
            "id": url,
            "metrics": {
                "INTERACTION_TO_NEXT_PAINT": {"percentile": inp_ms, "category": "AVERAGE"},
                "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": 2600, "category": "AVERAGE"},
            },
            "overall_category": "AVERAGE",
        }

    return payload


def quota_error() -> dict[str, Any]:
    return {
        "error": {
            "code": 429,
            "message": (
                "Quota exceeded for quota metric 'Queries' and limit 'Queries per day' of "
                "service 'pagespeedonline.googleapis.com'."
            ),
            "status": "RESOURCE_EXHAUSTED",
        }
    }


def unreachable_target_error() -> dict[str, Any]:
    return {
        "error": {
            "code": 400,
            "message": "Lighthouse returned error: ERRORED_DOCUMENT_REQUEST. Status code: 0",
            "status": "INVALID_ARGUMENT",
        }
    }
