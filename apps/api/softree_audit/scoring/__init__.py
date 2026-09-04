"""Motor de scoring.

Funciones puras, sin IO ni acceso a base de datos (`docs/spec/scoring.md` §9).
Ver `docs/spec/scoring.md` para la metodología y ADR-006 para las decisiones.
"""

from softree_audit.scoring.engine import (
    ScoreBreakdown,
    ScoreInput,
    SeoCoverage,
    SeverityTally,
    compute,
)
from softree_audit.scoring.weights import DEFAULT_WEIGHTS, normalize_weights

__all__ = [
    "DEFAULT_WEIGHTS",
    "ScoreBreakdown",
    "ScoreInput",
    "SeoCoverage",
    "SeverityTally",
    "compute",
    "normalize_weights",
]
