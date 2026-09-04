"""Motor de scoring (`docs/spec/scoring.md`, ADR-006).

Es una función pura: sin IO, sin base de datos y determinista.
"""

from __future__ import annotations

import pytest
from softree_audit.scoring import DEFAULT_WEIGHTS, ScoreInput, SeoCoverage, SeverityTally, compute
from softree_audit.scoring.engine import (
    band_of,
    lighthouse_score,
    security_score,
    seo_score,
)
from softree_audit.scoring.weights import normalize_weights

pytestmark = pytest.mark.unit


def tally(*items: tuple[str, str, int]) -> SeverityTally:
    result = SeverityTally()
    for severity, confidence, quantity in items:
        result.add(severity, confidence, quantity)
    return result


def perfect_seo() -> SeoCoverage:
    return SeoCoverage(
        ratios=dict.fromkeys(
            [
                "title_present",
                "title_unique",
                "description_present",
                "description_unique",
                "single_h1",
                "images_with_alt",
                "internal_links_ok",
                "canonical_ok",
                "site_files",
                "no_redirect_chains",
            ],
            1.0,
        )
    )


# ── Pesos ──────────────────────────────────────────────────────────────────


def test_default_weights_match_the_specification() -> None:
    """§26: 30 / 25 / 25 / 10 / 10."""
    assert DEFAULT_WEIGHTS == {
        "security": 0.30,
        "performance": 0.25,
        "seo": 0.25,
        "accessibility": 0.10,
        "best_practices": 0.10,
    }
    assert round(sum(DEFAULT_WEIGHTS.values()), 6) == 1.0


def test_missing_categories_redistribute_their_weight() -> None:
    """Una categoría sin datos no cuenta como cero (ADR-006)."""
    weights = normalize_weights(DEFAULT_WEIGHTS, {"security", "seo"})
    assert round(sum(weights.values()), 6) == 1.0
    # 30 y 25 se renormalizan manteniendo su proporción.
    assert weights["security"] == pytest.approx(0.30 / 0.55)
    assert weights["seo"] == pytest.approx(0.25 / 0.55)


def test_without_available_categories_there_are_no_weights() -> None:
    assert normalize_weights(DEFAULT_WEIGHTS, set()) == {}


def test_custom_weights_are_respected() -> None:
    custom = {"security": 0.8, "seo": 0.2}
    weights = normalize_weights(custom, {"security", "seo"})
    assert weights["security"] == pytest.approx(0.8)


# ── Seguridad ──────────────────────────────────────────────────────────────


def test_a_clean_site_scores_one_hundred() -> None:
    value, _ = security_score(SeverityTally())
    assert value == 100.0


def test_one_critical_with_high_confidence_costs_twenty_five_points() -> None:
    """§3: crítico penaliza 25 puntos con confianza alta."""
    value, detail = security_score(tally(("critical", "high", 1)))
    assert value == 75.0
    assert detail["total_penalty"] == 25.0


def test_confidence_reduces_the_penalty() -> None:
    high, _ = security_score(tally(("high", "high", 1)))
    medium, _ = security_score(tally(("high", "medium", 1)))
    low, _ = security_score(tally(("high", "low", 1)))
    assert high == 88.0  # 100 - 12
    assert medium == 91.0  # 100 - 12 * 0.75
    assert low == 94.0  # 100 - 12 * 0.5


def test_informational_findings_do_not_penalize() -> None:
    value, _ = security_score(tally(("info", "high", 50)))
    assert value == 100.0


def test_many_low_findings_cannot_dominate_the_score() -> None:
    """El techo por severidad evita que el ruido tape lo grave."""
    value, detail = security_score(tally(("low", "high", 100)))
    assert detail["penalties"]["low"] == 15.0
    assert value == 85.0


def test_each_severity_has_its_own_cap() -> None:
    value, detail = security_score(
        tally(("high", "high", 100), ("medium", "high", 100), ("low", "high", 100))
    )
    assert detail["penalties"] == {"high": 60.0, "medium": 35.0, "low": 15.0}
    assert value == 0.0


def test_the_score_never_goes_below_zero() -> None:
    value, _ = security_score(tally(("critical", "high", 20)))
    assert value == 0.0


# ── SEO ────────────────────────────────────────────────────────────────────


def test_perfect_coverage_scores_one_hundred() -> None:
    value, _ = seo_score(perfect_seo())
    assert value == 100.0


def test_a_failing_indicator_costs_its_weight() -> None:
    coverage = perfect_seo()
    coverage.ratios["single_h1"] = 0.0  # peso interno 15 %
    value, _ = seo_score(coverage)
    assert value == 85.0


def test_partial_coverage_is_proportional() -> None:
    coverage = perfect_seo()
    coverage.ratios["title_present"] = 0.5  # peso 15 %
    value, _ = seo_score(coverage)
    assert value == 92.5


def test_an_indicator_without_data_redistributes_its_weight() -> None:
    """Sin páginas evaluables el indicador no aplica, no vale cero."""
    coverage = perfect_seo()
    coverage.ratios["images_with_alt"] = None
    value, detail = seo_score(coverage)
    assert value == 100.0
    assert "images_with_alt" not in detail["indicators"]


def test_without_any_indicator_there_is_no_seo_score() -> None:
    value, detail = seo_score(SeoCoverage(ratios={}))
    assert value is None
    assert detail["reason"] == "sin_indicadores_evaluables"


# ── Lighthouse ─────────────────────────────────────────────────────────────


def test_mobile_and_desktop_are_combined_seventy_thirty() -> None:
    """§5: el tráfico de los sitios auditados es mayoritariamente móvil."""
    assert lighthouse_score({"mobile": 60, "desktop": 90}) == 69.0


def test_a_single_strategy_is_used_as_is() -> None:
    assert lighthouse_score({"mobile": 80}) == 80.0
    assert lighthouse_score({"desktop": 80}) == 80.0


def test_without_measurements_there_is_no_score() -> None:
    assert lighthouse_score({}) is None


# ── Score global ───────────────────────────────────────────────────────────


def test_a_perfect_scan_scores_one_hundred() -> None:
    result = compute(
        ScoreInput(
            security=SeverityTally(),
            seo=perfect_seo(),
            performance_by_strategy={"mobile": 100, "desktop": 100},
            accessibility_by_strategy={"mobile": 100},
            best_practices_by_strategy={"mobile": 100},
        )
    )
    assert result.overall == 100.0
    assert result.band == "excelente"
    assert round(sum(result.applied_weights.values()), 6) == 1.0


def test_the_overall_is_the_weighted_average() -> None:
    result = compute(
        ScoreInput(
            security=tally(("critical", "high", 1)),  # 75
            seo=perfect_seo(),  # 100
            performance_by_strategy={"mobile": 50},
            accessibility_by_strategy={"mobile": 80},
            best_practices_by_strategy={"mobile": 90},
        )
    )
    expected = 75 * 0.30 + 50 * 0.25 + 100 * 0.25 + 80 * 0.10 + 90 * 0.10
    assert result.overall == pytest.approx(expected, abs=0.05)


def test_a_missing_category_does_not_drag_the_score_down() -> None:
    """Que PageSpeed falle no debe empeorar el score del sitio."""
    with_performance = compute(
        ScoreInput(
            security=SeverityTally(), seo=perfect_seo(), performance_by_strategy={"mobile": 100}
        )
    )
    without_performance = compute(ScoreInput(security=SeverityTally(), seo=perfect_seo()))
    assert with_performance.overall == 100.0
    assert without_performance.overall == 100.0
    assert "performance" not in without_performance.applied_weights


def test_the_applied_weights_are_recorded_with_the_result() -> None:
    """Persistirlos hace que un cambio de configuración no altere el histórico."""
    result = compute(ScoreInput(security=SeverityTally(), seo=perfect_seo()))
    assert set(result.applied_weights) == {"security", "seo"}
    assert round(sum(result.applied_weights.values()), 6) == 1.0


def test_without_any_data_there_is_no_score() -> None:
    result = compute(ScoreInput())
    assert result.overall is None
    assert result.categories == {}


def test_the_calculation_is_deterministic() -> None:
    def build() -> ScoreInput:
        return ScoreInput(
            security=tally(("high", "medium", 3)),
            seo=perfect_seo(),
            performance_by_strategy={"mobile": 71, "desktop": 88},
        )

    assert compute(build()).overall == compute(build()).overall


@pytest.mark.parametrize(
    ("value", "band"),
    [
        (100.0, "excelente"),
        (90.0, "excelente"),
        (89.9, "bueno"),
        (75.0, "bueno"),
        (60.0, "mejorable"),
        (30.0, "deficiente"),
        (10.0, "critico"),
        (0.0, "critico"),
    ],
)
def test_interpretation_bands(value: float, band: str) -> None:
    assert band_of(value) == band


def test_custom_weights_change_the_result() -> None:
    """§26: los pesos no están escritos en el código de cálculo."""
    data = {
        "security": tally(("critical", "high", 1)),  # 75
        "seo": perfect_seo(),  # 100
    }
    balanced = compute(ScoreInput(security=data["security"], seo=data["seo"]))  # type: ignore[arg-type]
    security_heavy = compute(
        ScoreInput(
            security=data["security"],  # type: ignore[arg-type]
            seo=data["seo"],  # type: ignore[arg-type]
            weights={"security": 0.9, "seo": 0.1},
        )
    )
    assert security_heavy.overall < balanced.overall
