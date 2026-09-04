"""Tipos del análisis asistido por IA."""

from __future__ import annotations

from dataclasses import dataclass, field

# Cambiar el prompt cambia el texto que produce el modelo. La versión se
# persiste con cada análisis para poder explicar por qué dos auditorías
# parecidas recibieron redacciones distintas.
PROMPT_VERSION = "v1"


@dataclass(slots=True)
class AiRecommendation:
    """Una recomendación priorizada."""

    title: str
    detail: str
    priority: str  # alta | media | baja


@dataclass(slots=True)
class AiResult:
    """Salida del analizador, ya normalizada."""

    summary: str
    recommendations: list[AiRecommendation] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    model: str = ""
    prompt_version: str = PROMPT_VERSION
    duration_ms: int | None = None
    tokens_prompt: int | None = None
    tokens_completion: int | None = None
