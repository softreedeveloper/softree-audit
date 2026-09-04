"""Findings y scores de Google derivados de PageSpeed Insights.

Dos salidas distintas y deliberadamente separadas (§27, ADR-006):

- **Google Score**: las puntuaciones de Lighthouse tal cual, sin transformar.
- **Findings**: incidencias derivadas de superar los umbrales públicos de
  Google, que alimentarán el Softree Score en el Slice 8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from softree_audit.models.enums import (
    Confidence,
    FindingSource,
    PageSpeedStrategy,
    ScoreCategory,
    Severity,
)
from softree_audit.services.findings.models import NormalizedFinding
from softree_audit.services.performance import thresholds
from softree_audit.services.performance.catalog import CATALOG, PerformanceRule
from softree_audit.services.performance.models import PageSpeedResult
from softree_audit.services.performance.thresholds import Band

# Una métrica en zona mala es una incidencia media; en zona de mejora, leve.
BAND_SEVERITY: dict[Band, Severity] = {
    Band.POOR: Severity.MEDIUM,
    Band.NEEDS_IMPROVEMENT: Severity.LOW,
}

# La estrategia que manda en el score agregado. Softree audita sobre todo sitios
# con tráfico mayoritariamente móvil (`docs/spec/scoring.md` §5).
PRIMARY_STRATEGY = PageSpeedStrategy.MOBILE


@dataclass(slots=True)
class GoogleScore:
    """Puntuación de Lighthouse, sin transformar."""

    category: ScoreCategory
    value: int
    strategy: PageSpeedStrategy


@dataclass(slots=True)
class PerformanceAnalysis:
    results: list[PageSpeedResult] = field(default_factory=list)
    findings: list[NormalizedFinding] = field(default_factory=list)
    google_scores: list[GoogleScore] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            "strategies_analyzed": [result.strategy.value for result in self.results],
            "from_cache": [result.strategy.value for result in self.results if result.from_cache],
            "has_field_data": any(result.has_field_data for result in self.results),
            "lighthouse_version": next(
                (result.lighthouse_version for result in self.results if result.lighthouse_version),
                None,
            ),
            "findings": len(self.findings),
            "google_scores": {
                f"{score.category.value}_{score.strategy.value}": score.value
                for score in self.google_scores
            },
            "failures": self.failures,
        }


def _finding(
    rule: PerformanceRule,
    *,
    url: str,
    severity: Severity,
    evidence: str,
    strategy: PageSpeedStrategy,
    confidence: Confidence = Confidence.HIGH,
) -> NormalizedFinding:
    return NormalizedFinding(
        source=FindingSource.PAGESPEED,
        category=rule.category,
        rule_id=rule.id,
        title=f"{rule.title} ({strategy.value})",
        severity=severity,
        confidence=confidence,
        url=url,
        # El parámetro distingue móvil de escritorio en la huella: son medidas
        # distintas del mismo problema y ambas deben poder verse.
        parameter=strategy.value,
        evidence=evidence,
        description=rule.description,
        impact=rule.impact,
        remediation=rule.remediation,
        client_explanation=rule.client_explanation,
        references=["https://developers.google.com/speed/docs/insights/v5/about"],
    )


def _metric_findings(result: PageSpeedResult) -> list[NormalizedFinding]:
    findings: list[NormalizedFinding] = []

    checks: list[tuple[str, float | None, thresholds.Threshold, str]] = [
        (
            "PSI-002",
            float(result.lcp_ms) if result.lcp_ms is not None else None,
            thresholds.LCP,
            "LCP",
        ),
        ("PSI-003", float(result.cls) if result.cls is not None else None, thresholds.CLS, "CLS"),
        (
            "PSI-005",
            float(result.tbt_ms) if result.tbt_ms is not None else None,
            thresholds.TBT,
            "TBT",
        ),
    ]
    if result.inp_ms is not None:
        checks.append(("PSI-004", float(result.inp_ms), thresholds.INP, "INP"))

    for rule_id, value, threshold, label in checks:
        band = threshold.band(value)
        if band is None or band is Band.GOOD or value is None:
            continue
        shown = (
            f"{value:.3f}".rstrip("0").rstrip(".") if threshold.unit == "" else f"{value:.0f} ms"
        )
        findings.append(
            _finding(
                CATALOG[rule_id],
                url=result.url,
                severity=BAND_SEVERITY[band],
                strategy=result.strategy,
                evidence=(
                    f"{label} = {shown}. Umbral recomendado: "
                    f"{threshold.good:g}{threshold.unit or ''}."
                ),
            )
        )
    return findings


def _category_findings(result: PageSpeedResult) -> list[NormalizedFinding]:
    findings: list[NormalizedFinding] = []
    checks = [
        ("PSI-001", result.performance_score, "rendimiento"),
        ("PSI-006", result.accessibility_score, "accesibilidad"),
        ("PSI-007", result.best_practices_score, "buenas prácticas"),
        ("PSI-008", result.seo_score, "SEO"),
    ]

    for rule_id, score, label in checks:
        band = thresholds.category_band(score)
        if band is None or band is Band.GOOD or score is None:
            continue
        findings.append(
            _finding(
                CATALOG[rule_id],
                url=result.url,
                severity=Severity.MEDIUM if band is Band.POOR else Severity.LOW,
                strategy=result.strategy,
                evidence=(
                    f"Puntuación de {label}: {score}/100. "
                    f"Google considera buena una puntuación de {thresholds.CATEGORY_GOOD} o más."
                ),
            )
        )
    return findings


SCORE_CATEGORIES: list[tuple[str, ScoreCategory]] = [
    ("performance_score", ScoreCategory.PERFORMANCE),
    ("accessibility_score", ScoreCategory.ACCESSIBILITY),
    ("best_practices_score", ScoreCategory.BEST_PRACTICES),
    ("seo_score", ScoreCategory.SEO),
]


def google_scores(results: list[PageSpeedResult]) -> list[GoogleScore]:
    """Puntuaciones de Lighthouse, sin transformación alguna (§27)."""
    scores: list[GoogleScore] = []
    for result in results:
        for attribute, category in SCORE_CATEGORIES:
            value = getattr(result, attribute)
            if value is not None:
                scores.append(
                    GoogleScore(category=category, value=int(value), strategy=result.strategy)
                )
    return scores


def analyze(results: list[PageSpeedResult]) -> PerformanceAnalysis:
    analysis = PerformanceAnalysis(results=list(results))
    for result in results:
        analysis.findings.extend(_category_findings(result))
        analysis.findings.extend(_metric_findings(result))
    analysis.google_scores = google_scores(results)
    return analysis
