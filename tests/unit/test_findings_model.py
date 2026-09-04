"""Modelo unificado de findings y deduplicación (§18, §25)."""

from __future__ import annotations

import pytest
from softree_audit.models.enums import FindingCategory, FindingSource, Severity
from softree_audit.services.findings.dedupe import deduplicate
from softree_audit.services.findings.models import NormalizedFinding, build_fingerprint

pytestmark = pytest.mark.unit


def finding(**overrides: object) -> NormalizedFinding:
    defaults: dict[str, object] = {
        "source": FindingSource.SEO,
        "category": FindingCategory.SEO,
        "title": "Título de prueba",
        "severity": Severity.MEDIUM,
        "description": "Descripción",
        "rule_id": "SEO-001",
        "url": "https://softree.mx/pagina",
    }
    return NormalizedFinding(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_fingerprint_is_stable() -> None:
    assert finding().fingerprint == finding().fingerprint


def test_fingerprint_distinguishes_rule_url_and_parameter() -> None:
    base = finding().fingerprint
    assert finding(rule_id="SEO-003").fingerprint != base
    assert finding(url="https://softree.mx/otra").fingerprint != base
    assert finding(parameter="titulo").fingerprint != base
    assert finding(source=FindingSource.ZAP).fingerprint != base


def test_fingerprint_ignores_url_variants() -> None:
    """`/a`, `/a/` y `/a#x` son la misma página: no deben duplicar el hallazgo."""
    base = finding(url="https://softree.mx/a").fingerprint
    assert finding(url="https://softree.mx/a/").fingerprint == base
    assert finding(url="https://softree.mx/a#seccion").fingerprint == base
    assert finding(url="https://SOFTREE.mx/a").fingerprint == base


def test_fingerprint_falls_back_to_category_without_rule() -> None:
    first = build_fingerprint(
        source=FindingSource.ZAP,
        rule_id=None,
        category=FindingCategory.SECURITY,
        url="https://softree.mx/",
        parameter=None,
    )
    second = build_fingerprint(
        source=FindingSource.ZAP,
        rule_id=None,
        category=FindingCategory.SECURITY,
        url="https://softree.mx/",
        parameter=None,
    )
    assert first == second


def test_long_evidence_is_truncated() -> None:
    result = finding(evidence="x" * 10_000)
    assert result.evidence is not None
    assert len(result.evidence) <= 4000


def test_deduplicate_merges_equivalent_findings() -> None:
    merged = deduplicate([finding(), finding(), finding()])
    assert len(merged) == 1
    assert merged[0].occurrences == 3


def test_deduplicate_keeps_distinct_findings() -> None:
    merged = deduplicate([finding(), finding(rule_id="SEO-003"), finding(url="https://x.test/")])
    assert len(merged) == 3


def test_deduplicate_preserves_order() -> None:
    merged = deduplicate(
        [finding(rule_id="SEO-005"), finding(rule_id="SEO-001"), finding(rule_id="SEO-005")]
    )
    assert [item.rule_id for item in merged] == ["SEO-005", "SEO-001"]


def test_deduplicate_accumulates_occurrences() -> None:
    merged = deduplicate([finding(occurrences=2), finding(occurrences=5)])
    assert merged[0].occurrences == 7


def test_deduplicate_of_nothing_is_empty() -> None:
    assert deduplicate([]) == []
