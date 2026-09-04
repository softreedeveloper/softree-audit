"""Normalización de la respuesta de PageSpeed Insights."""

from __future__ import annotations

import decimal

import pytest
from softree_audit.models.enums import PageSpeedStrategy
from softree_audit.services.performance.normalizer import has_field_data, normalize

from tests.fixtures import pagespeed

pytestmark = pytest.mark.unit

URL = "https://softree.mx/"


def normalized(**overrides: object):
    payload = pagespeed.response(**overrides)  # type: ignore[arg-type]
    return normalize(payload, url=URL, strategy=PageSpeedStrategy.MOBILE)


def test_scores_are_converted_to_percentages() -> None:
    """Lighthouse devuelve de 0 a 1; se presenta de 0 a 100."""
    result = normalized()
    assert result.performance_score == 87
    assert result.accessibility_score == 92
    assert result.best_practices_score == 96
    assert result.seo_score == 100


def test_lab_metrics_are_rounded_to_milliseconds() -> None:
    result = normalized()
    assert result.lcp_ms == 2450
    assert result.fcp_ms == 1200
    assert result.tbt_ms == 150
    assert result.speed_index_ms == 3300


def test_cls_keeps_its_decimals() -> None:
    """CLS no es un tiempo: redondearlo a entero lo destruiría."""
    result = normalized(cls=0.1234)
    assert result.cls == decimal.Decimal("0.1234")


def test_lighthouse_version_is_recorded() -> None:
    assert normalized().lighthouse_version == "12.2.1"


def test_raw_response_is_kept_for_traceability() -> None:
    """Requisito §21: se guarda la respuesta original."""
    result = normalized()
    assert result.raw["lighthouseResult"]["lighthouseVersion"] == "12.2.1"


def test_without_field_data_inp_is_none_not_zero() -> None:
    """Requisito R4: `null` significa «sin datos de campo», nunca cero."""
    result = normalized()
    assert result.inp_ms is None
    assert result.has_field_data is False


def test_with_field_data_inp_is_read_from_crux() -> None:
    result = normalized(inp_ms=340)
    assert result.inp_ms == 340
    assert result.has_field_data is True


def test_missing_categories_do_not_break_normalization() -> None:
    result = normalized(accessibility=None, seo=None)
    assert result.performance_score == 87
    assert result.accessibility_score is None
    assert result.seo_score is None


def test_missing_audits_do_not_break_normalization() -> None:
    result = normalized(lcp_ms=None, tbt_ms=None)
    assert result.lcp_ms is None
    assert result.tbt_ms is None
    assert result.fcp_ms == 1200


def test_empty_payload_produces_an_empty_result() -> None:
    result = normalize({}, url=URL, strategy=PageSpeedStrategy.DESKTOP)
    assert result.performance_score is None
    assert result.lcp_ms is None
    assert result.strategy is PageSpeedStrategy.DESKTOP


def test_malformed_payload_does_not_raise() -> None:
    payload = {"lighthouseResult": "no es un objeto", "loadingExperience": 42}
    result = normalize(payload, url=URL, strategy=PageSpeedStrategy.MOBILE)
    assert result.performance_score is None


def test_scores_are_clamped_to_the_valid_range() -> None:
    result = normalized(performance=1.5)
    assert result.performance_score == 100


def test_has_field_data_helper() -> None:
    assert has_field_data(pagespeed.response(inp_ms=200)) is True
    assert has_field_data(pagespeed.response()) is False
    assert has_field_data({"loadingExperience": {"metrics": {}}}) is False
