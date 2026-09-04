"""Traducción del scope de Softree al contexto de ZAP.

ZAP emite sus propias peticiones y no pasa por el guard de SSRF de la
aplicación, así que el alcance se inyecta también como expresiones de inclusión
y exclusión en su contexto: doble barrera (`docs/spec/requirements.md` R6).
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit


def _escape(value: str) -> str:
    return re.escape(value)


def include_patterns(base_url: str, allowed_domains: tuple[str, ...]) -> list[str]:
    """Expresiones de inclusión: el dominio y sus subdominios, en http y https."""
    patterns: list[str] = []
    for domain in allowed_domains:
        escaped = _escape(domain)
        # `dominio` y `*.dominio`, con puerto opcional.
        patterns.append(rf"^https?://([^/@]+\.)?{escaped}(:\d+)?(/.*)?$")

    if not patterns:
        # Sin dominios declarados, el único alcance seguro es la propia URL base.
        patterns.append(rf"^{_escape(base_url.rstrip('/'))}(/.*)?$")
    return patterns


def exclude_patterns(
    allowed_domains: tuple[str, ...], excluded_paths: tuple[str, ...]
) -> list[str]:
    """Expresiones de exclusión para las rutas vetadas del scope."""
    patterns: list[str] = []
    for domain in allowed_domains:
        escaped_domain = _escape(domain)
        for path in excluded_paths:
            normalized = "/" + path.strip("/")
            escaped_path = _escape(normalized)
            # La ruta excluida y todo lo que cuelgue de ella.
            patterns.append(rf"^https?://([^/@]+\.)?{escaped_domain}(:\d+)?{escaped_path}(/.*)?$")
    return patterns


def matches_any(url: str, patterns: list[str]) -> bool:
    return any(re.match(pattern, url) for pattern in patterns)


def is_in_zap_scope(url: str, includes: list[str], excludes: list[str]) -> bool:
    """Réplica local de la decisión de ZAP, usada en las pruebas."""
    if not urlsplit(url).scheme.startswith("http"):
        return False
    if matches_any(url, excludes):
        return False
    return matches_any(url, includes)
