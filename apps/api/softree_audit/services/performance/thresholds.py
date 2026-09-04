"""Umbrales de Core Web Vitals y de las categorías de Lighthouse.

Son los umbrales públicos de Google, no criterios propios: se declaran aquí para
que estén en un solo sitio y sean revisables cuando Google los cambie.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Band(StrEnum):
    GOOD = "good"
    NEEDS_IMPROVEMENT = "needs_improvement"
    POOR = "poor"


@dataclass(frozen=True, slots=True)
class Threshold:
    """Un valor menor o igual a `good` es bueno; mayor que `poor` es malo."""

    good: float
    needs_improvement: float
    unit: str = "ms"

    def band(self, value: float | None) -> Band | None:
        if value is None:
            return None
        if value <= self.good:
            return Band.GOOD
        if value <= self.needs_improvement:
            return Band.NEEDS_IMPROVEMENT
        return Band.POOR


# Core Web Vitals (web.dev/vitals).
LCP = Threshold(good=2500, needs_improvement=4000)
CLS = Threshold(good=0.1, needs_improvement=0.25, unit="")
INP = Threshold(good=200, needs_improvement=500)
FCP = Threshold(good=1800, needs_improvement=3000)
TBT = Threshold(good=200, needs_improvement=600)
SPEED_INDEX = Threshold(good=3400, needs_improvement=5800)

# Bandas de las categorías de Lighthouse, expresadas de 0 a 100.
CATEGORY_GOOD = 90
CATEGORY_NEEDS_IMPROVEMENT = 50


def category_band(score: int | None) -> Band | None:
    if score is None:
        return None
    if score >= CATEGORY_GOOD:
        return Band.GOOD
    if score >= CATEGORY_NEEDS_IMPROVEMENT:
        return Band.NEEDS_IMPROVEMENT
    return Band.POOR
