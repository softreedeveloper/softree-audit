"""Traducción del scope al contexto de ZAP (doble barrera, R6)."""

from __future__ import annotations

import pytest
from softree_audit.services.security.scope_regex import (
    exclude_patterns,
    include_patterns,
    is_in_zap_scope,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]

BASE = "https://softree.mx"
DOMAINS = ("softree.mx",)


def scope(
    domains: tuple[str, ...] = DOMAINS, excluded: tuple[str, ...] = ()
) -> tuple[list[str], list[str]]:
    return include_patterns(BASE, domains), exclude_patterns(domains, excluded)


@pytest.mark.parametrize(
    "url",
    [
        "https://softree.mx/",
        "https://softree.mx/blog/entrada",
        "http://softree.mx/",
        "https://www.softree.mx/",
        "https://a.b.softree.mx/x",
        "https://softree.mx:8443/x",
    ],
)
def test_urls_of_the_site_are_in_scope(url: str) -> None:
    includes, excludes = scope()
    assert is_in_zap_scope(url, includes, excludes) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://otro-dominio.test/",
        # El sufijo debe respetar el límite de etiqueta.
        "https://malicioso-softree.mx/",
        "https://softree.mx.malicioso.test/",
        # Confusión por credenciales: el host real es malicioso.test.
        "https://softree.mx@malicioso.test/",
        "ftp://softree.mx/",
        "file:///etc/passwd",
    ],
)
def test_urls_outside_the_site_are_not_in_scope(url: str) -> None:
    includes, excludes = scope()
    assert is_in_zap_scope(url, includes, excludes) is False


def test_excluded_paths_are_removed_from_scope() -> None:
    includes, excludes = scope(excluded=("/admin",))
    assert is_in_zap_scope("https://softree.mx/publico", includes, excludes) is True
    assert is_in_zap_scope("https://softree.mx/admin", includes, excludes) is False
    assert is_in_zap_scope("https://softree.mx/admin/panel", includes, excludes) is False


def test_exclusion_respects_segment_boundaries() -> None:
    """Excluir `/admin` no debe excluir `/administracion`."""
    includes, excludes = scope(excluded=("/admin",))
    assert is_in_zap_scope("https://softree.mx/administracion", includes, excludes) is True


def test_exclusion_applies_to_every_allowed_domain() -> None:
    includes, excludes = scope(domains=("softree.mx", "otro.test"), excluded=("/privado",))
    assert is_in_zap_scope("https://otro.test/privado/x", includes, excludes) is False
    assert is_in_zap_scope("https://otro.test/publico", includes, excludes) is True


def test_without_domains_only_the_base_url_is_in_scope() -> None:
    includes, excludes = scope(domains=())
    assert is_in_zap_scope("https://softree.mx/x", includes, excludes) is True
    assert is_in_zap_scope("https://otro.test/", includes, excludes) is False


def test_regex_metacharacters_in_a_domain_are_escaped() -> None:
    """Un punto en el dominio no debe funcionar como comodín."""
    includes, excludes = scope(domains=("softree.mx",))
    assert is_in_zap_scope("https://softreeXmx/", includes, excludes) is False
