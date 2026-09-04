"""Traducción de los artefactos del scan a la entrada del motor de scoring.

El motor es puro; esta capa es la que sabe de findings, agregados SEO y
resultados de PageSpeed.
"""

from __future__ import annotations

from typing import Any

from softree_audit.models.enums import FindingCategory, FindingStatus
from softree_audit.scoring import ScoreInput, SeoCoverage, SeverityTally
from softree_audit.services.findings.models import NormalizedFinding
from softree_audit.services.performance.models import PageSpeedResult
from softree_audit.services.seo.aggregates import SeoAggregates


def security_tally(
    findings: list[NormalizedFinding], statuses: dict[str, FindingStatus]
) -> SeverityTally:
    """Cuenta los findings de seguridad **abiertos**.

    Un hallazgo marcado como corregido, aceptado o falso positivo no penaliza
    (`docs/spec/scoring.md` §3).
    """
    tally = SeverityTally()
    for finding in findings:
        if finding.category is not FindingCategory.SECURITY:
            continue
        if statuses.get(finding.fingerprint, FindingStatus.OPEN) is not FindingStatus.OPEN:
            continue
        tally.add(finding.severity.value, finding.confidence.value)
    return tally


def _ratio(conforming: int, evaluable: int) -> float | None:
    """Razón conforme/evaluable. Sin páginas evaluables, el indicador no aplica."""
    if evaluable <= 0:
        return None
    return max(0.0, min(1.0, conforming / evaluable))


def seo_coverage(aggregates: SeoAggregates) -> SeoCoverage:
    """Convierte los agregados SEO en las razones que espera el motor."""
    pages = aggregates.pages_crawled
    images = aggregates.images_missing_alt

    return SeoCoverage(
        ratios={
            "title_present": _ratio(pages - aggregates.missing_title, pages),
            "title_unique": _ratio(pages - aggregates.duplicate_title, pages),
            "description_present": _ratio(pages - aggregates.missing_description, pages),
            "description_unique": _ratio(pages - aggregates.duplicate_description, pages),
            "single_h1": _ratio(pages - aggregates.missing_h1 - aggregates.multiple_h1, pages),
            # Sin imágenes el indicador no aplica; suponer 100 % premiaría un
            # sitio por no tener imágenes.
            "images_with_alt": None if images == 0 and pages == 0 else _images_ratio(aggregates),
            "internal_links_ok": _ratio(pages - aggregates.broken_internal_links, pages),
            "canonical_ok": _ratio(pages - aggregates.missing_canonical, pages),
            "site_files": _ratio(
                int(aggregates.robots_txt_found) + int(aggregates.sitemap_found), 2
            ),
            "no_redirect_chains": _ratio(pages - aggregates.redirect_chains, pages),
        }
    )


def _images_ratio(aggregates: SeoAggregates) -> float | None:
    """Proporción de imágenes con texto alternativo.

    Los agregados guardan cuántas faltan, no el total; se aproxima con las
    páginas que las contienen. Si no hay ninguna carencia, el indicador es
    perfecto.
    """
    if aggregates.images_missing_alt == 0:
        return 1.0 if aggregates.pages_crawled > 0 else None
    # Cada imagen sin alt penaliza, acotado a la escala del sitio.
    denominator = max(aggregates.images_missing_alt, aggregates.pages_crawled)
    return _ratio(denominator - aggregates.images_missing_alt, denominator)


def lighthouse_by_strategy(results: list[PageSpeedResult], attribute: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for result in results:
        score = getattr(result, attribute)
        if score is not None:
            values[result.strategy.value] = int(score)
    return values


def build_input(
    *,
    findings: list[NormalizedFinding],
    statuses: dict[str, FindingStatus],
    aggregates: SeoAggregates | None,
    performance: list[PageSpeedResult],
    weights: dict[str, float],
) -> ScoreInput:
    """Arma la entrada del motor con lo que el scan haya producido.

    Las categorías sin datos se dejan fuera para que su peso se redistribuya en
    lugar de contar como cero (ADR-006).
    """
    has_security = any(finding.category is FindingCategory.SECURITY for finding in findings)

    return ScoreInput(
        security=security_tally(findings, statuses) if has_security else None,
        seo=seo_coverage(aggregates) if aggregates is not None else None,
        performance_by_strategy=lighthouse_by_strategy(performance, "performance_score"),
        accessibility_by_strategy=lighthouse_by_strategy(performance, "accessibility_score"),
        best_practices_by_strategy=lighthouse_by_strategy(performance, "best_practices_score"),
        weights=dict(weights),
    )


def summary(breakdown: Any) -> dict[str, Any]:
    return {
        "overall": breakdown.overall,
        "band": breakdown.band,
        "categories": breakdown.categories,
        "applied_weights": breakdown.applied_weights,
    }
