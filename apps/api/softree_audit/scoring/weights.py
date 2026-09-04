"""Pesos del Softree Score.

Los pesos son configurables y nunca están escritos en el código de cálculo
(§26). Si falta una categoría, su peso se redistribuye proporcionalmente entre
las disponibles en lugar de contar como cero: penalizar al sitio por la caída de
una API externa haría el score no reproducible (ADR-006).
"""

from __future__ import annotations

DEFAULT_WEIGHTS: dict[str, float] = {
    "security": 0.30,
    "performance": 0.25,
    "seo": 0.25,
    "accessibility": 0.10,
    "best_practices": 0.10,
}


def normalize_weights(weights: dict[str, float], available: set[str]) -> dict[str, float]:
    """Renormaliza los pesos a las categorías con datos.

    Devuelve un diccionario cuyos valores suman 1. Si no hay ninguna categoría
    disponible, devuelve un diccionario vacío.
    """
    usable = {
        category: weight
        for category, weight in weights.items()
        if category in available and weight > 0
    }
    total = sum(usable.values())
    if total <= 0:
        return {}
    return {category: weight / total for category, weight in usable.items()}
