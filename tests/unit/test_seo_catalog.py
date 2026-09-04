"""Integridad del catálogo de reglas SEO."""

from __future__ import annotations

import pytest
from softree_audit.models.enums import FindingCategory, Severity
from softree_audit.services.seo.catalog import CATALOG
from softree_audit.services.seo.rules import RULES

pytestmark = pytest.mark.unit

EXPECTED_IDS = tuple(f"SEO-{number:03d}" for number in range(1, 17))


def test_the_sixteen_rules_of_the_spec_exist() -> None:
    """`docs/spec/requirements.md` RF-08 enumera SEO-001 a SEO-016."""
    assert tuple(CATALOG) == EXPECTED_IDS


def test_every_definition_has_an_implementation() -> None:
    assert set(RULES) == set(CATALOG)


def test_every_rule_has_the_two_reading_levels() -> None:
    """El reporte necesita detalle técnico y explicación para el cliente (§34)."""
    for rule in CATALOG.values():
        assert rule.description.strip(), rule.id
        assert rule.impact.strip(), rule.id
        assert rule.remediation.strip(), rule.id
        assert rule.client_explanation.strip(), rule.id


def test_client_explanations_avoid_markup_and_jargon() -> None:
    for rule in CATALOG.values():
        assert "<" not in rule.client_explanation, rule.id
        assert len(rule.client_explanation) < 400, rule.id


def test_severities_are_valid() -> None:
    for rule in CATALOG.values():
        assert rule.severity in set(Severity), rule.id


def test_images_without_alt_counts_as_accessibility() -> None:
    """Es antes accesibilidad que posicionamiento, y así alimenta ese score."""
    assert CATALOG["SEO-007"].category is FindingCategory.ACCESSIBILITY


def test_rules_that_may_be_intentional_have_lower_confidence() -> None:
    from softree_audit.models.enums import Confidence

    # Un noindex suele ser deliberado; un enlace externo puede fallar por el otro lado.
    assert CATALOG["SEO-012"].confidence is Confidence.MEDIUM
    assert CATALOG["SEO-009"].confidence is Confidence.MEDIUM
