"""Análisis asistido por IA sobre una auditoría ya normalizada.

El analizador recibe hallazgos y puntuaciones, nunca emite tráfico hacia el
sitio auditado y no modifica el estado de ningún hallazgo
(`docs/spec/reports.md` §8).
"""

from softree_audit.services.ai.client import (
    AiClient,
    AiError,
    AiNotConfiguredError,
    AiTransientError,
)
from softree_audit.services.ai.models import AiRecommendation, AiResult
from softree_audit.services.ai.prompt import build_messages

__all__ = [
    "AiClient",
    "AiError",
    "AiNotConfiguredError",
    "AiRecommendation",
    "AiResult",
    "AiTransientError",
    "build_messages",
]
