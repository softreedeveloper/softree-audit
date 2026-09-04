"""Comparación entre auditorías (§32)."""

from __future__ import annotations

import pytest
from softree_audit.comparison.engine import (
    ChangeKind,
    FindingSnapshot,
    compare,
    compare_findings,
    compare_metrics,
)

pytestmark = pytest.mark.unit


def snapshot(
    fingerprint: str,
    *,
    severity: str = "medium",
    occurrences: int = 1,
    is_open: bool = True,
    rule_id: str = "SEO-001",
    source: str = "seo",
) -> FindingSnapshot:
    return FindingSnapshot(
        fingerprint=fingerprint,
        rule_id=rule_id,
        title=f"Hallazgo {fingerprint}",
        severity=severity,
        category="seo",
        occurrences=occurrences,
        source=source,
        is_open=is_open,
    )


def kinds(changes: list[object]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for change in changes:
        result.setdefault(change.kind.value, []).append(change.fingerprint)  # type: ignore[attr-defined]
    return result


# ── Clasificación de hallazgos ─────────────────────────────────────────────


def test_a_finding_that_only_exists_now_is_new() -> None:
    changes = compare_findings([], [snapshot("a")])
    assert changes[0].kind is ChangeKind.NEW


def test_a_finding_that_disappeared_is_fixed() -> None:
    changes = compare_findings([snapshot("a")], [])
    assert changes[0].kind is ChangeKind.FIXED
    assert changes[0].previous_occurrences == 1
    assert changes[0].occurrences == 0


def test_a_finding_present_in_both_is_unchanged() -> None:
    changes = compare_findings([snapshot("a")], [snapshot("a")])
    assert changes[0].kind is ChangeKind.UNCHANGED


def test_a_worse_severity_is_a_regression() -> None:
    changes = compare_findings(
        [snapshot("a", severity="low")], [snapshot("a", severity="critical")]
    )
    assert changes[0].kind is ChangeKind.REGRESSED
    assert changes[0].previous_severity == "low"


def test_more_cases_of_the_same_finding_is_a_regression() -> None:
    """El mismo problema en más páginas es un empeoramiento."""
    changes = compare_findings([snapshot("a", occurrences=2)], [snapshot("a", occurrences=9)])
    assert changes[0].kind is ChangeKind.REGRESSED
    assert changes[0].previous_occurrences == 2


def test_fewer_cases_is_not_a_regression() -> None:
    changes = compare_findings([snapshot("a", occurrences=9)], [snapshot("a", occurrences=2)])
    assert changes[0].kind is ChangeKind.UNCHANGED


def test_a_lower_severity_is_not_a_regression() -> None:
    changes = compare_findings([snapshot("a", severity="high")], [snapshot("a", severity="low")])
    assert changes[0].kind is ChangeKind.UNCHANGED


def test_resolved_findings_are_ignored_on_both_sides() -> None:
    """Un hallazgo aceptado no debe aparecer como corregido ni como nuevo."""
    changes = compare_findings([snapshot("a", is_open=False)], [snapshot("a", is_open=False)])
    assert changes == []


def test_accepting_a_finding_reads_as_fixed_in_the_comparison() -> None:
    """Si deja de estar abierto, deja de contar como problema pendiente."""
    changes = compare_findings([snapshot("a")], [snapshot("a", is_open=False)])
    assert changes[0].kind is ChangeKind.FIXED


def test_a_complete_comparison() -> None:
    previous = [snapshot("igual"), snapshot("resuelto"), snapshot("peor", severity="low")]
    current = [snapshot("igual"), snapshot("nuevo"), snapshot("peor", severity="high")]

    changes = compare_findings(previous, current)
    grouped = kinds(changes)

    assert grouped["new"] == ["nuevo"]
    assert grouped["fixed"] == ["resuelto"]
    assert grouped["unchanged"] == ["igual"]
    assert grouped["regressed"] == ["peor"]


def test_regressions_come_first() -> None:
    """Lo que empeoró es lo primero que hay que mirar."""
    changes = compare_findings(
        [snapshot("peor", severity="low"), snapshot("igual")],
        [snapshot("peor", severity="high"), snapshot("igual"), snapshot("nuevo")],
    )
    assert changes[0].kind is ChangeKind.REGRESSED


def test_counts_summarize_the_comparison() -> None:
    result = compare(
        previous_findings=[snapshot("a"), snapshot("b")],
        current_findings=[snapshot("a"), snapshot("c")],
        previous_metrics={},
        current_metrics={},
    )
    assert result.counts() == {"new": 1, "fixed": 1, "unchanged": 1, "regressed": 0}


# ── Deltas de métricas ─────────────────────────────────────────────────────


def test_a_higher_score_is_an_improvement() -> None:
    deltas = compare_metrics({"softree_overall": 70.0}, {"softree_overall": 86.0})
    assert deltas[0].delta == 16.0
    assert deltas[0].direction == "mejora"


def test_a_lower_score_is_a_worsening() -> None:
    deltas = compare_metrics({"softree_overall": 90.0}, {"softree_overall": 60.0})
    assert deltas[0].direction == "empeora"


def test_fewer_broken_links_is_an_improvement() -> None:
    """En los contadores de errores, menos es mejor."""
    deltas = compare_metrics({"broken_internal_links": 12.0}, {"broken_internal_links": 3.0})
    assert deltas[0].delta == -9.0
    assert deltas[0].direction == "mejora"


def test_a_faster_lcp_is_an_improvement() -> None:
    deltas = compare_metrics({"lcp_ms": 3100.0}, {"lcp_ms": 2200.0})
    assert deltas[0].direction == "mejora"


def test_an_unchanged_metric_is_reported_as_equal() -> None:
    deltas = compare_metrics({"missing_title": 4.0}, {"missing_title": 4.0})
    assert deltas[0].direction == "igual"


def test_a_metric_missing_on_one_side_has_no_delta() -> None:
    """Sin dato en un lado no se puede afirmar que mejoró ni que empeoró."""
    deltas = compare_metrics({"lcp_ms": 2000.0}, {})
    assert deltas[0].delta is None
    assert deltas[0].direction == "desconocido"


def test_metrics_absent_from_both_scans_are_omitted() -> None:
    assert compare_metrics({}, {}) == []


def test_metric_order_follows_the_declared_specification() -> None:
    deltas = compare_metrics(
        {"softree_overall": 1.0, "missing_title": 1.0},
        {"softree_overall": 2.0, "missing_title": 0.0},
    )
    assert [delta.key for delta in deltas] == ["softree_overall", "missing_title"]


# ── Fuentes comparables ────────────────────────────────────────────────────


def test_only_sources_measured_by_both_scans_are_compared() -> None:
    """Comparar un scan SEO con uno completo reportaría lo de ZAP como corregido."""
    previous = [snapshot("seo-1"), snapshot("zap-1", source="zap")]
    current = [snapshot("seo-1")]

    result = compare(
        previous_findings=previous,
        current_findings=current,
        previous_metrics={},
        current_metrics={},
        previous_sources={"seo", "zap"},
        current_sources={"seo"},
    )

    assert result.counts()["fixed"] == 0
    assert result.counts()["unchanged"] == 1
    assert result.compared_sources == ["seo"]
    assert result.sources_only_in_previous == ["zap"]


def test_a_source_added_in_the_new_scan_is_declared() -> None:
    result = compare(
        previous_findings=[snapshot("seo-1")],
        current_findings=[snapshot("seo-1"), snapshot("zap-1", source="zap")],
        previous_metrics={},
        current_metrics={},
        previous_sources={"seo"},
        current_sources={"seo", "zap"},
    )
    assert result.counts()["new"] == 0
    assert result.sources_only_in_current == ["zap"]


def test_with_the_same_sources_everything_is_compared() -> None:
    result = compare(
        previous_findings=[snapshot("seo-1"), snapshot("zap-1", source="zap")],
        current_findings=[snapshot("seo-1")],
        previous_metrics={},
        current_metrics={},
        previous_sources={"seo", "zap"},
        current_sources={"seo", "zap"},
    )
    assert result.counts()["fixed"] == 1


def test_without_source_information_nothing_is_filtered() -> None:
    result = compare(
        previous_findings=[snapshot("a")],
        current_findings=[],
        previous_metrics={},
        current_metrics={},
    )
    assert result.counts()["fixed"] == 1
    assert result.compared_sources == []
