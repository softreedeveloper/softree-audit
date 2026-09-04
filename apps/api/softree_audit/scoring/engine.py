"""Cálculo del Softree Score.

Entrada: conteos y coberturas ya calculados por quien llama. El motor no toca la
base de datos ni la red, de modo que el mismo dato produce siempre el mismo
resultado (`docs/spec/scoring.md` §9).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from softree_audit.scoring.weights import DEFAULT_WEIGHTS, normalize_weights

# Penalización por finding abierto y techo acumulado, en puntos sobre 100
# (`docs/spec/scoring.md` §3).
SECURITY_PENALTY: dict[str, float] = {
    "critical": 25.0,
    "high": 12.0,
    "medium": 5.0,
    "low": 2.0,
    "info": 0.0,
}
SECURITY_PENALTY_CAP: dict[str, float] = {
    "critical": 100.0,
    "high": 60.0,
    "medium": 35.0,
    "low": 15.0,
    "info": 0.0,
}

# Un hallazgo de confianza baja pesa menos que uno confirmado.
CONFIDENCE_FACTOR: dict[str, float] = {"high": 1.0, "medium": 0.75, "low": 0.5}

# Peso interno de cada indicador SEO (`docs/spec/scoring.md` §4).
SEO_INDICATOR_WEIGHTS: dict[str, float] = {
    "title_present": 0.15,
    "title_unique": 0.10,
    "description_present": 0.10,
    "description_unique": 0.05,
    "single_h1": 0.15,
    "images_with_alt": 0.10,
    "internal_links_ok": 0.15,
    "canonical_ok": 0.10,
    "site_files": 0.05,
    "no_redirect_chains": 0.05,
}

# Proporción móvil/escritorio del score de rendimiento (§5).
MOBILE_WEIGHT = 0.70
DESKTOP_WEIGHT = 0.30

BANDS: tuple[tuple[float, str], ...] = (
    (90.0, "excelente"),
    (75.0, "bueno"),
    (50.0, "mejorable"),
    (25.0, "deficiente"),
    (0.0, "critico"),
)


def band_of(value: float | None) -> str | None:
    if value is None:
        return None
    for threshold, label in BANDS:
        if value >= threshold:
            return label
    return "critico"


@dataclass(slots=True)
class SeverityTally:
    """Findings abiertos por severidad y confianza."""

    counts: dict[tuple[str, str], int] = field(default_factory=dict)

    def add(self, severity: str, confidence: str, quantity: int = 1) -> None:
        key = (severity.lower(), confidence.lower())
        self.counts[key] = self.counts.get(key, 0) + quantity

    @property
    def total(self) -> int:
        return sum(self.counts.values())


@dataclass(slots=True)
class SeoCoverage:
    """Razón `conforme / evaluable` de cada indicador SEO.

    Un indicador sin páginas evaluables se declara `None` y su peso se
    redistribuye entre los demás.
    """

    ratios: dict[str, float | None] = field(default_factory=dict)


@dataclass(slots=True)
class ScoreInput:
    security: SeverityTally | None = None
    seo: SeoCoverage | None = None
    # Puntuaciones de Lighthouse de 0 a 100, por estrategia.
    performance_by_strategy: dict[str, int] = field(default_factory=dict)
    accessibility_by_strategy: dict[str, int] = field(default_factory=dict)
    best_practices_by_strategy: dict[str, int] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))


@dataclass(slots=True)
class ScoreBreakdown:
    overall: float | None
    categories: dict[str, float] = field(default_factory=dict)
    applied_weights: dict[str, float] = field(default_factory=dict)
    detail: dict[str, object] = field(default_factory=dict)

    @property
    def band(self) -> str | None:
        return band_of(self.overall)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def security_score(tally: SeverityTally) -> tuple[float, dict[str, object]]:
    """Parte de 100 y descuenta por finding abierto, con techo por severidad."""
    penalties: dict[str, float] = {}

    for severity, penalty in SECURITY_PENALTY.items():
        if penalty <= 0:
            continue
        accumulated = 0.0
        for (found_severity, confidence), quantity in tally.counts.items():
            if found_severity != severity:
                continue
            factor = CONFIDENCE_FACTOR.get(confidence, 0.75)
            accumulated += penalty * factor * quantity
        if accumulated:
            penalties[severity] = min(accumulated, SECURITY_PENALTY_CAP[severity])

    total_penalty = sum(penalties.values())
    return _clamp(100.0 - total_penalty), {
        "penalties": {key: round(value, 2) for key, value in penalties.items()},
        "total_penalty": round(total_penalty, 2),
        "findings": tally.total,
    }


def seo_score(coverage: SeoCoverage) -> tuple[float | None, dict[str, object]]:
    """Media ponderada de los indicadores con datos."""
    available = {
        indicator
        for indicator, ratio in coverage.ratios.items()
        if ratio is not None and indicator in SEO_INDICATOR_WEIGHTS
    }
    weights = normalize_weights(SEO_INDICATOR_WEIGHTS, available)
    if not weights:
        return None, {"reason": "sin_indicadores_evaluables"}

    value = sum(
        _clamp((coverage.ratios[key] or 0.0) * 100) * weight for key, weight in weights.items()
    )
    return round(value, 1), {
        "indicators": {
            key: round((coverage.ratios[key] or 0.0) * 100, 1) for key in sorted(weights)
        },
        "weights": {key: round(weight, 4) for key, weight in sorted(weights.items())},
    }


def lighthouse_score(by_strategy: dict[str, int]) -> float | None:
    """Combina móvil y escritorio con la proporción declarada en §5."""
    mobile = by_strategy.get("mobile")
    desktop = by_strategy.get("desktop")

    if mobile is not None and desktop is not None:
        return round(mobile * MOBILE_WEIGHT + desktop * DESKTOP_WEIGHT, 1)
    if mobile is not None:
        return float(mobile)
    if desktop is not None:
        return float(desktop)
    return None


def compute(data: ScoreInput) -> ScoreBreakdown:
    """Calcula el Softree Score a partir de los datos de un scan."""
    categories: dict[str, float] = {}
    detail: dict[str, object] = {}

    if data.security is not None:
        value, security_detail = security_score(data.security)
        categories["security"] = round(value, 1)
        detail["security"] = security_detail

    if data.seo is not None:
        value_or_none, seo_detail = seo_score(data.seo)
        if value_or_none is not None:
            categories["seo"] = value_or_none
        detail["seo"] = seo_detail

    for category, source in (
        ("performance", data.performance_by_strategy),
        ("accessibility", data.accessibility_by_strategy),
        ("best_practices", data.best_practices_by_strategy),
    ):
        lighthouse = lighthouse_score(source)
        if lighthouse is not None:
            categories[category] = lighthouse
            detail[category] = {"by_strategy": dict(source)}

    weights = normalize_weights(data.weights, set(categories))
    if not weights:
        return ScoreBreakdown(overall=None, categories={}, applied_weights={}, detail=detail)

    overall = sum(categories[category] * weight for category, weight in weights.items())
    return ScoreBreakdown(
        overall=round(overall, 1),
        categories=categories,
        applied_weights={key: round(value, 4) for key, value in weights.items()},
        detail=detail,
    )
