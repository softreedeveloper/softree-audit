"""Traducción de los artefactos del scan a la entrada del motor de scoring."""

from __future__ import annotations

import pytest
from softree_audit.models.enums import (
    Confidence,
    FindingCategory,
    FindingSource,
    FindingStatus,
    PageSpeedStrategy,
    Severity,
)
from softree_audit.scans.scoring_inputs import (
    build_input,
    lighthouse_by_strategy,
    security_tally,
    seo_coverage,
)
from softree_audit.services.findings.models import NormalizedFinding
from softree_audit.services.performance.models import PageSpeedResult
from softree_audit.services.seo.aggregates import SeoAggregates

pytestmark = pytest.mark.unit


def finding(
    *,
    category: FindingCategory = FindingCategory.SECURITY,
    severity: Severity = Severity.HIGH,
    confidence: Confidence = Confidence.HIGH,
    rule_id: str = "10038-1",
    url: str | None = None,
) -> NormalizedFinding:
    return NormalizedFinding(
        source=FindingSource.ZAP,
        category=category,
        rule_id=rule_id,
        title="Hallazgo",
        severity=severity,
        confidence=confidence,
        description="Descripción",
        url=url,
    )


def test_only_security_findings_feed_the_security_score() -> None:
    findings = [
        finding(),
        finding(category=FindingCategory.SEO, rule_id="SEO-001"),
        finding(category=FindingCategory.PERFORMANCE, rule_id="PSI-001"),
    ]
    assert security_tally(findings, {}).total == 1


def test_resolved_findings_do_not_penalize() -> None:
    """§3: solo los abiertos cuentan."""
    open_finding = finding(rule_id="abierto")
    accepted = finding(rule_id="aceptado")
    statuses = {accepted.fingerprint: FindingStatus.ACCEPTED}
    assert security_tally([open_finding, accepted], statuses).total == 1


@pytest.mark.parametrize(
    "status",
    [FindingStatus.FIXED, FindingStatus.ACCEPTED, FindingStatus.FALSE_POSITIVE],
)
def test_every_resolved_state_is_excluded(status: FindingStatus) -> None:
    item = finding()
    assert security_tally([item], {item.fingerprint: status}).total == 0


def test_severity_and_confidence_are_preserved() -> None:
    tally = security_tally([finding(severity=Severity.MEDIUM, confidence=Confidence.LOW)], {})
    assert tally.counts == {("medium", "low"): 1}


# ── Cobertura SEO ──────────────────────────────────────────────────────────


def aggregates(**overrides: object) -> SeoAggregates:
    defaults: dict[str, object] = {
        "pages_crawled": 10,
        "urls_discovered": 10,
        "robots_txt_found": True,
        "sitemap_found": True,
    }
    return SeoAggregates(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_a_clean_site_has_full_coverage() -> None:
    coverage = seo_coverage(aggregates())
    assert coverage.ratios["title_present"] == 1.0
    assert coverage.ratios["single_h1"] == 1.0
    assert coverage.ratios["site_files"] == 1.0


def test_missing_titles_reduce_their_indicator() -> None:
    coverage = seo_coverage(aggregates(missing_title=3))
    assert coverage.ratios["title_present"] == pytest.approx(0.7)


def test_missing_site_files_reduce_their_indicator() -> None:
    coverage = seo_coverage(aggregates(sitemap_found=False))
    assert coverage.ratios["site_files"] == 0.5
    coverage = seo_coverage(aggregates(sitemap_found=False, robots_txt_found=False))
    assert coverage.ratios["site_files"] == 0.0


def test_pages_with_several_h1_also_fail_the_indicator() -> None:
    coverage = seo_coverage(aggregates(missing_h1=1, multiple_h1=2))
    assert coverage.ratios["single_h1"] == pytest.approx(0.7)


def test_without_crawled_pages_the_indicators_do_not_apply() -> None:
    """Sin datos no se puede afirmar nada: el peso se redistribuye."""
    coverage = seo_coverage(aggregates(pages_crawled=0))
    assert coverage.ratios["title_present"] is None
    assert coverage.ratios["single_h1"] is None


def test_a_site_without_images_is_not_rewarded_nor_punished() -> None:
    coverage = seo_coverage(aggregates(images_missing_alt=0))
    assert coverage.ratios["images_with_alt"] == 1.0


# ── Lighthouse ─────────────────────────────────────────────────────────────


def test_lighthouse_scores_are_grouped_by_strategy() -> None:
    results = [
        PageSpeedResult(
            url="https://x.test/", strategy=PageSpeedStrategy.MOBILE, performance_score=62
        ),
        PageSpeedResult(
            url="https://x.test/", strategy=PageSpeedStrategy.DESKTOP, performance_score=91
        ),
    ]
    assert lighthouse_by_strategy(results, "performance_score") == {
        "mobile": 62,
        "desktop": 91,
    }


def test_missing_scores_are_omitted_not_zeroed() -> None:
    results = [
        PageSpeedResult(
            url="https://x.test/",
            strategy=PageSpeedStrategy.MOBILE,
            accessibility_score=None,
        )
    ]
    assert lighthouse_by_strategy(results, "accessibility_score") == {}


# ── Entrada completa ───────────────────────────────────────────────────────


def test_build_input_omits_categories_without_data() -> None:
    data = build_input(
        findings=[finding(category=FindingCategory.SEO, rule_id="SEO-001")],
        statuses={},
        aggregates=None,
        performance=[],
        weights={"security": 0.5, "seo": 0.5},
    )
    # No hay hallazgos de seguridad ni agregados SEO ni medidas de PageSpeed.
    assert data.security is None
    assert data.seo is None
    assert data.performance_by_strategy == {}


def test_build_input_includes_what_the_scan_produced() -> None:
    data = build_input(
        findings=[finding()],
        statuses={},
        aggregates=aggregates(),
        performance=[
            PageSpeedResult(
                url="https://x.test/",
                strategy=PageSpeedStrategy.MOBILE,
                performance_score=70,
                accessibility_score=90,
                best_practices_score=95,
            )
        ],
        weights={"security": 0.3, "seo": 0.7},
    )
    assert data.security is not None
    assert data.seo is not None
    assert data.performance_by_strategy == {"mobile": 70}
    assert data.accessibility_by_strategy == {"mobile": 90}
    assert data.best_practices_by_strategy == {"mobile": 95}
