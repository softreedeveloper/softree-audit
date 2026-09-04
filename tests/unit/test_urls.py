"""Normalización de URL, hosts y rutas (`services/common/urls.py`)."""

from __future__ import annotations

import pytest
from softree_audit.services.common.urls import (
    InvalidHostnameError,
    InvalidPathError,
    InvalidUrlError,
    hostname_of,
    matches_domain,
    matches_path,
    normalize_hostname,
    normalize_path,
    normalize_url,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://Softree.mx", "https://softree.mx"),
        ("https://softree.mx/", "https://softree.mx"),
        ("https://softree.mx:443", "https://softree.mx"),
        ("http://softree.mx:80/", "http://softree.mx"),
        ("https://softree.mx:8443/app", "https://softree.mx:8443/app"),
        ("https://softree.mx/blog/", "https://softree.mx/blog"),
        ("https://softree.mx/#seccion", "https://softree.mx"),
        ("https://softree.mx/?utm_source=x", "https://softree.mx"),
        ("  https://softree.mx  ", "https://softree.mx"),
        ("https://SOFTREE.mx./", "https://softree.mx"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "softree.mx",
        "ftp://softree.mx",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://",
        "https:// softree.mx",
        "https://softree.mx:99999",
    ],
)
def test_normalize_url_rejects_invalid_input(raw: str) -> None:
    with pytest.raises(InvalidUrlError):
        normalize_url(raw)


@pytest.mark.security
def test_normalize_url_rejects_embedded_credentials() -> None:
    """`https://usuario:clave@host` confunde host real y aparente."""
    with pytest.raises(InvalidUrlError):
        normalize_url("https://admin:secreto@softree.mx")


@pytest.mark.security
def test_normalize_url_rejects_credential_confusion() -> None:
    """`https://softree.mx@malicioso.test` apunta en realidad a malicioso.test."""
    with pytest.raises(InvalidUrlError):
        normalize_url("https://softree.mx@malicioso.test")


def test_normalize_url_length_limit() -> None:
    with pytest.raises(InvalidUrlError):
        normalize_url("https://softree.mx/" + "a" * 2100)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Softree.MX", "softree.mx"),
        ("softree.mx.", "softree.mx"),
        ("  softree.mx ", "softree.mx"),
        ("192.168.1.1", "192.168.1.1"),
        ("[::1]", "[::1]"),
        ("xn--espaa-rta.com", "xn--espaa-rta.com"),
    ],
)
def test_normalize_hostname(raw: str, expected: str) -> None:
    assert normalize_hostname(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "softree mx",
        "softree.mx/ruta",
        "-softree.mx",
        "softree-.mx",
        "http://softree.mx",
        "a" * 300,
    ],
)
def test_normalize_hostname_rejects_invalid_input(raw: str) -> None:
    with pytest.raises(InvalidHostnameError):
        normalize_hostname(raw)


def test_hostname_of() -> None:
    assert hostname_of("https://www.softree.mx/blog") == "www.softree.mx"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("/", "/"), ("/blog", "/blog"), ("/blog/", "/blog"), ("  /blog  ", "/blog")],
)
def test_normalize_path(raw: str, expected: str) -> None:
    assert normalize_path(raw) == expected


@pytest.mark.parametrize("raw", ["blog", "", "/blog/*", "/blog?x=1", "/../etc", "/con espacio"])
def test_normalize_path_rejects_invalid_input(raw: str) -> None:
    with pytest.raises(InvalidPathError):
        normalize_path(raw)


@pytest.mark.security
@pytest.mark.parametrize(
    ("host", "domain", "expected"),
    [
        ("softree.mx", "softree.mx", True),
        ("www.softree.mx", "softree.mx", True),
        ("a.b.softree.mx", "softree.mx", True),
        # El sufijo debe respetar el límite de etiqueta.
        ("malicioso-softree.mx", "softree.mx", False),
        ("softree.mx.malicioso.test", "softree.mx", False),
        ("softree.com", "softree.mx", False),
        ("softree.mx", "www.softree.mx", False),
    ],
)
def test_matches_domain(host: str, domain: str, expected: bool) -> None:
    assert matches_domain(host, domain) is expected


@pytest.mark.security
@pytest.mark.parametrize(
    ("path", "prefix", "expected"),
    [
        ("/blog/entrada", "/", True),
        ("/blog", "/blog", True),
        ("/blog/", "/blog", True),
        ("/blog/entrada", "/blog", True),
        # El prefijo debe respetar el límite de segmento.
        ("/blogsecreto", "/blog", False),
        ("/otra", "/blog", False),
    ],
)
def test_matches_path(path: str, prefix: str, expected: bool) -> None:
    assert matches_path(path, prefix) is expected
