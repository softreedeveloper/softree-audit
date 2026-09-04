"""Findings y puntuaciones de Google derivados de PageSpeed."""

from __future__ import annotations

import decimal

import pytest
from softree_audit.models.enums import (
    FindingCategory,
    FindingSource,
    PageSpeedStrategy,
    ScoreCategory,
    Severity,
)
from softree_audit.services.performance import thresholds
from softree_audit.services.performance.engine import analyze, google_scores
from softree_audit.services.performance.models import PageSpeedResult
from softree_audit.services.performance.thresholds import Band, category_band

pytestmark = pytest.mark.unit

URL = "https://softree.mx/"


def result(**overrides: object) -> PageSpeedResult:
    defaults: dict[str, object] = {
        "url": URL,
        "strategy": PageSpeedStrategy.MOBILE,
        "performance_score": 95,
        "accessibility_score": 95,
        "best_practices_score": 95,
        "seo_score": 95,
        "lcp_ms": 2000,
        "cls": decimal.Decimal("0.05"),
        "tbt_ms": 100,
        "fcp_ms": 1000,
        "speed_index_ms": 2000,
    }
    return PageSpeedResult(**{**defaults, **overrides})  # type: ignore[arg-type]


def rule_ids(analysis_result: object) -> list[str]:
    return [f.rule_id for f in analysis_result.findings]  # type: ignore[attr-defined]


# ── Umbrales ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [(2400, Band.GOOD), (2500, Band.GOOD), (3000, Band.NEEDS_IMPROVEMENT), (4500, Band.POOR)],
)
def test_lcp_bands(value: int, expected: Band) -> None:
    assert thresholds.LCP.band(value) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.05, Band.GOOD), (0.1, Band.GOOD), (0.2, Band.NEEDS_IMPROVEMENT), (0.4, Band.POOR)],
)
def test_cls_bands(value: float, expected: Band) -> None:
    assert thresholds.CLS.band(value) is expected


@pytest.mark.parametrize(
    ("score", "expected"),
    [(100, Band.GOOD), (90, Band.GOOD), (70, Band.NEEDS_IMPROVEMENT), (30, Band.POOR)],
)
def test_category_bands(score: int, expected: Band) -> None:
    assert category_band(score) is expected


def test_missing_value_has_no_band() -> None:
    assert thresholds.LCP.band(None) is None
    assert category_band(None) is None


# ── Findings ───────────────────────────────────────────────────────────────


def test_a_healthy_page_produces_no_findings() -> None:
    assert analyze([result()]).findings == []


def test_poor_performance_score_produces_a_finding() -> None:
    analysis = analyze([result(performance_score=35)])
    assert "PSI-001" in rule_ids(analysis)
    finding = next(f for f in analysis.findings if f.rule_id == "PSI-001")
    assert finding.severity is Severity.MEDIUM
    assert finding.source is FindingSource.PAGESPEED
    assert "35/100" in (finding.evidence or "")


def test_score_in_the_middle_band_is_a_low_severity_finding() -> None:
    analysis = analyze([result(performance_score=70)])
    finding = next(f for f in analysis.findings if f.rule_id == "PSI-001")
    assert finding.severity is Severity.LOW


def test_high_lcp_produces_a_finding_with_the_threshold_in_the_evidence() -> None:
    analysis = analyze([result(lcp_ms=5200)])
    finding = next(f for f in analysis.findings if f.rule_id == "PSI-002")
    assert finding.severity is Severity.MEDIUM
    assert "5200 ms" in (finding.evidence or "")
    assert "2500" in (finding.evidence or "")


def test_high_cls_is_reported_without_millisecond_units() -> None:
    analysis = analyze([result(cls=decimal.Decimal("0.35"))])
    finding = next(f for f in analysis.findings if f.rule_id == "PSI-003")
    assert "0.35" in (finding.evidence or "")
    assert "ms" not in (finding.evidence or "")


def test_inp_is_only_evaluated_when_there_is_field_data() -> None:
    """Sin datos de campo no hay INP: inventar un valor sería falsear el dato."""
    assert "PSI-004" not in rule_ids(analyze([result(inp_ms=None)]))
    assert "PSI-004" in rule_ids(analyze([result(inp_ms=700, has_field_data=True)]))


def test_accessibility_finding_uses_the_accessibility_category() -> None:
    analysis = analyze([result(accessibility_score=40)])
    finding = next(f for f in analysis.findings if f.rule_id == "PSI-006")
    assert finding.category is FindingCategory.ACCESSIBILITY


def test_best_practices_and_lighthouse_seo_use_their_own_categories() -> None:
    analysis = analyze([result(best_practices_score=40, seo_score=40)])
    categories = {f.rule_id: f.category for f in analysis.findings}
    assert categories["PSI-007"] is FindingCategory.BEST_PRACTICES
    assert categories["PSI-008"] is FindingCategory.SEO


def test_mobile_and_desktop_are_separate_findings() -> None:
    """Son medidas distintas del mismo problema y ambas deben poder verse."""
    analysis = analyze(
        [
            result(performance_score=40, strategy=PageSpeedStrategy.MOBILE),
            result(performance_score=40, strategy=PageSpeedStrategy.DESKTOP),
        ]
    )
    psi001 = [f for f in analysis.findings if f.rule_id == "PSI-001"]
    assert len(psi001) == 2
    assert {f.parameter for f in psi001} == {"mobile", "desktop"}
    assert len({f.fingerprint for f in psi001}) == 2


def test_findings_reference_the_official_documentation() -> None:
    finding = analyze([result(performance_score=10)]).findings[0]
    assert any("developers.google.com" in str(ref) for ref in finding.references)


def test_every_finding_has_both_reading_levels() -> None:
    analysis = analyze([result(performance_score=10, accessibility_score=10, lcp_ms=9000)])
    for finding in analysis.findings:
        assert finding.impact
        assert finding.remediation
        assert finding.client_explanation


# ── Google Score ───────────────────────────────────────────────────────────


def test_google_scores_are_not_transformed() -> None:
    """§27: la puntuación de Lighthouse se presenta tal cual."""
    scores = google_scores([result(performance_score=87, accessibility_score=92)])
    values = {(score.category, score.strategy): score.value for score in scores}
    assert values[(ScoreCategory.PERFORMANCE, PageSpeedStrategy.MOBILE)] == 87
    assert values[(ScoreCategory.ACCESSIBILITY, PageSpeedStrategy.MOBILE)] == 92


def test_google_scores_cover_both_strategies() -> None:
    scores = google_scores(
        [
            result(strategy=PageSpeedStrategy.MOBILE, performance_score=60),
            result(strategy=PageSpeedStrategy.DESKTOP, performance_score=90),
        ]
    )
    performance = [s for s in scores if s.category is ScoreCategory.PERFORMANCE]
    assert {(s.strategy, s.value) for s in performance} == {
        (PageSpeedStrategy.MOBILE, 60),
        (PageSpeedStrategy.DESKTOP, 90),
    }


def test_missing_scores_are_not_reported_as_zero() -> None:
    scores = google_scores([result(accessibility_score=None)])
    assert all(score.category is not ScoreCategory.ACCESSIBILITY for score in scores)


def test_summary_reports_what_was_analyzed() -> None:
    analysis = analyze([result(), result(strategy=PageSpeedStrategy.DESKTOP)])
    summary = analysis.summary()
    assert summary["strategies_analyzed"] == ["mobile", "desktop"]
    assert summary["findings"] == 0
    assert summary["has_field_data"] is False
