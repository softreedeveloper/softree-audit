"""Validación del scope (`schemas/scope.py`)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from softree_audit.models.site import (
    MAX_CONCURRENCY,
    MAX_DEPTH_LIMIT,
    MAX_PAGES_LIMIT,
    MAX_TIMEOUT_SECONDS,
)
from softree_audit.schemas.scope import ScopeLimits, ScopeUpdate

pytestmark = pytest.mark.unit

BASE: dict[str, object] = {"allowed_domains": ["softree.mx"]}


def test_defaults_are_conservative() -> None:
    scope = ScopeUpdate(**BASE)  # type: ignore[arg-type]
    assert scope.max_pages == 200
    assert scope.max_depth == 3
    assert scope.concurrency == 4
    assert scope.request_delay_ms == 200
    assert scope.respect_robots is True
    assert scope.allowed_paths == []
    assert scope.excluded_paths == []


def test_domains_are_normalized_and_deduplicated() -> None:
    scope = ScopeUpdate(allowed_domains=["Softree.MX", "softree.mx.", "www.softree.mx"])
    assert scope.allowed_domains == ["softree.mx", "www.softree.mx"]


def test_paths_are_normalized_and_deduplicated() -> None:
    scope = ScopeUpdate(**BASE, allowed_paths=["/blog/", "/blog", "/docs"])  # type: ignore[arg-type]
    assert scope.allowed_paths == ["/blog", "/docs"]


def test_at_least_one_domain_is_required() -> None:
    with pytest.raises(ValidationError):
        ScopeUpdate(allowed_domains=[])


def test_invalid_domain_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        ScopeUpdate(allowed_domains=["https://softree.mx/ruta"])
    assert "Dominio inválido" in str(excinfo.value)


def test_path_without_leading_slash_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        ScopeUpdate(**BASE, allowed_paths=["blog"])  # type: ignore[arg-type]
    assert "Ruta inválida" in str(excinfo.value)


@pytest.mark.security
def test_wildcards_are_rejected() -> None:
    """La comparación es por prefijo; un comodín ampliaría el alcance real."""
    with pytest.raises(ValidationError):
        ScopeUpdate(**BASE, excluded_paths=["/admin/*"])  # type: ignore[arg-type]


@pytest.mark.security
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_pages", MAX_PAGES_LIMIT + 1),
        ("max_depth", MAX_DEPTH_LIMIT + 1),
        ("timeout_seconds", MAX_TIMEOUT_SECONDS + 1),
        ("concurrency", MAX_CONCURRENCY + 1),
        ("max_pages", 0),
        ("concurrency", 0),
        ("request_delay_ms", -1),
    ],
)
def test_limits_cannot_be_exceeded(field: str, value: int) -> None:
    """El usuario puede bajar los límites, nunca superarlos."""
    with pytest.raises(ValidationError):
        ScopeUpdate(**BASE, **{field: value})  # type: ignore[arg-type]


def test_reported_limits_match_the_database_constraints() -> None:
    """La interfaz consulta los máximos a la API; deben ser los mismos."""
    limits = ScopeLimits()
    assert limits.max_pages == MAX_PAGES_LIMIT
    assert limits.max_depth == MAX_DEPTH_LIMIT
    assert limits.timeout_seconds == MAX_TIMEOUT_SECONDS
    assert limits.concurrency == MAX_CONCURRENCY


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ScopeUpdate(**BASE, ignorar_robots=True)  # type: ignore[arg-type]
