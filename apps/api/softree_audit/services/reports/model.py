"""Modelo de datos del reporte.

Es la única fuente de la que se generan PDF, HTML y JSON (ADR-007). Cualquier
dato que aparezca en un formato tiene que estar aquí.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Any

# Aviso obligatorio de metodología (`docs/spec/reports.md` §5).
METHODOLOGY_DISCLAIMER = (
    "Los indicadores identificados como «Google Lighthouse» provienen de la API pública "
    "de Google PageSpeed Insights. El «Softree Score» es un indicador propio de Softree y "
    "no constituye una calificación oficial de Google."
)

AI_DISCLAIMER = (
    "El apartado «Análisis asistido por IA» lo redactó un modelo de lenguaje a partir de los "
    "hallazgos de esta misma auditoría. No añade mediciones ni sustituye el criterio del "
    "consultor: revíselo antes de entregarlo."
)

SCOPE_DISCLAIMER = (
    "El análisis de seguridad es pasivo: examina las respuestas del sitio sin enviarle "
    "peticiones de ataque. No cubre todas las clases de vulnerabilidad, y la ausencia de "
    "hallazgos no significa que el sitio esté libre de riesgos."
)


@dataclass(slots=True)
class ReportFinding:
    rule_id: str | None
    title: str
    severity: str
    confidence: str
    category: str
    source: str
    url: str | None
    occurrences: int
    description: str
    impact: str | None
    remediation: str | None
    client_explanation: str | None
    evidence: str | None
    cwe: str | None
    owasp: str | None


@dataclass(slots=True)
class ReportSection:
    key: str
    title: str
    module_status: str
    summary: dict[str, Any] = field(default_factory=dict)
    findings: list[ReportFinding] = field(default_factory=list)
    note: str | None = None


@dataclass(slots=True)
class ReportComparison:
    previous_scan_id: str
    previous_finished_at: dt.datetime | None
    counts: dict[str, int]
    metrics: list[dict[str, Any]]
    compared_sources: list[str]
    sources_only_in_previous: list[str]


@dataclass(slots=True)
class AiRecommendationBlock:
    title: str
    detail: str
    priority: str


@dataclass(slots=True)
class ReportAnalysis:
    """Análisis redactado por el modelo de lenguaje.

    Va siempre acompañado de su procedencia: el reporte debe dejar claro qué
    parte del texto la escribió una máquina (`docs/spec/reports.md` §8).
    """

    summary: str
    recommendations: list[AiRecommendationBlock] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    model: str = ""
    generated_at: dt.datetime | None = None


@dataclass(slots=True)
class ReportModel:
    """Todo lo que el reporte muestra, en un único objeto."""

    # Portada
    scan_id: str
    site_name: str
    site_base_url: str
    project_name: str
    client_name: str | None
    generated_at: dt.datetime
    period_start: dt.datetime | None
    period_end: dt.datetime | None

    app_version: str
    engine_version: str
    report_version: str

    # Resumen
    softree_overall: float | None
    band: str | None
    softree_categories: dict[str, float] = field(default_factory=dict)
    applied_weights: dict[str, float] = field(default_factory=dict)
    google_scores: dict[str, float] = field(default_factory=dict)
    findings_by_severity: dict[str, int] = field(default_factory=dict)

    sections: list[ReportSection] = field(default_factory=list)
    recommendations: list[ReportFinding] = field(default_factory=list)
    comparison: ReportComparison | None = None
    ai_analysis: ReportAnalysis | None = None

    pages_crawled: int = 0
    urls_discovered: int = 0
    scan_duration_ms: int | None = None
    modules: list[dict[str, Any]] = field(default_factory=list)

    methodology_disclaimer: str = METHODOLOGY_DISCLAIMER
    scope_disclaimer: str = SCOPE_DISCLAIMER
    ai_disclaimer: str = AI_DISCLAIMER

    @property
    def total_findings(self) -> int:
        return sum(self.findings_by_severity.values())

    def as_dict(self) -> dict[str, Any]:
        """Serialización usada tal cual por el formato JSON."""
        data = asdict(self)
        data["generated_at"] = self.generated_at.isoformat()
        data["period_start"] = self.period_start.isoformat() if self.period_start else None
        data["period_end"] = self.period_end.isoformat() if self.period_end else None
        if self.comparison is not None:
            comparison = data["comparison"]
            comparison["previous_finished_at"] = (
                self.comparison.previous_finished_at.isoformat()
                if self.comparison.previous_finished_at
                else None
            )
        if self.ai_analysis is not None and self.ai_analysis.generated_at is not None:
            data["ai_analysis"]["generated_at"] = self.ai_analysis.generated_at.isoformat()
        data["total_findings"] = self.total_findings
        return data
