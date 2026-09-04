"""Estructuras del módulo de rendimiento."""

from __future__ import annotations

import decimal
from dataclasses import dataclass, field
from typing import Any

from softree_audit.models.enums import PageSpeedStrategy


@dataclass(slots=True)
class PageSpeedResult:
    """Resultado de PageSpeed Insights para una URL y estrategia."""

    url: str
    strategy: PageSpeedStrategy

    performance_score: int | None = None
    accessibility_score: int | None = None
    best_practices_score: int | None = None
    seo_score: int | None = None

    lcp_ms: int | None = None
    cls: decimal.Decimal | None = None
    # INP solo existe con datos de campo (CrUX). `None` significa «sin datos»,
    # nunca cero (requisito R4).
    inp_ms: int | None = None
    fcp_ms: int | None = None
    tbt_ms: int | None = None
    speed_index_ms: int | None = None

    lighthouse_version: str | None = None
    has_field_data: bool = False
    from_cache: bool = False

    # Respuesta original completa, para trazabilidad (§21).
    raw: dict[str, Any] = field(default_factory=dict)

    def as_row(self) -> dict[str, Any]:
        """Campos tal como se persisten en `performance_results`."""
        return {
            "url": self.url,
            "strategy": self.strategy,
            "performance_score": self.performance_score,
            "accessibility_score": self.accessibility_score,
            "best_practices_score": self.best_practices_score,
            "seo_score": self.seo_score,
            "lcp_ms": self.lcp_ms,
            "cls": self.cls,
            "inp_ms": self.inp_ms,
            "fcp_ms": self.fcp_ms,
            "tbt_ms": self.tbt_ms,
            "speed_index_ms": self.speed_index_ms,
            "lighthouse_version": self.lighthouse_version,
            "has_field_data": self.has_field_data,
            "raw": self.raw,
        }
