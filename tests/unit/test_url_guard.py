"""Guard de SSRF (`docs/spec/security.md` §2).

Es el control de seguridad más importante del producto: la plataforma asume que
el target puede ser malicioso, y que un usuario pueda introducir una URL no
significa que el servidor pueda conectarse a cualquier IP.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from softree_audit.services.common.url_guard import (
    BlockedTargetError,
    GuardPolicy,
    ScopePolicy,
    UrlGuard,
)

pytestmark = [pytest.mark.unit, pytest.mark.security]


def resolver_returning(*addresses: str):
    async def _resolve(host: str, port: int) -> Sequence[str]:
        return list(addresses)

    return _resolve


async def failing_resolver(host: str, port: int) -> Sequence[str]:
    raise OSError("sin resolución")


def guard(*addresses: str, **policy: object) -> UrlGuard:
    return UrlGuard(
        GuardPolicy(**policy),  # type: ignore[arg-type]
        resolver=resolver_returning(*addresses or ("93.184.216.34",)),
    )


# ── Camino feliz ───────────────────────────────────────────────────────────


async def test_public_address_is_allowed() -> None:
    target = await guard("93.184.216.34").validate("https://softree.mx/blog")
    assert target.host == "softree.mx"
    assert target.port == 443
    assert str(target.ip) == "93.184.216.34"
    assert target.url == "https://softree.mx/blog"


async def test_pinned_host_is_the_validated_address() -> None:
    """La conexión debe ir a la IP validada, no a una nueva resolución."""
    target = await guard("93.184.216.34").validate("https://softree.mx")
    assert target.pinned_host == "93.184.216.34"


async def test_ipv6_pinned_host_is_bracketed() -> None:
    target = await guard("2606:2800:220:1:248:1893:25c8:1946").validate("https://softree.mx")
    assert target.pinned_host == "[2606:2800:220:1:248:1893:25c8:1946]"


# ── Rangos bloqueados ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("address", "label"),
    [
        ("127.0.0.1", "loopback"),
        ("127.1.2.3", "loopback ampliado"),
        ("::1", "loopback IPv6"),
        ("10.1.2.3", "privada clase A"),
        ("172.16.0.5", "privada clase B"),
        ("172.31.255.255", "privada clase B, límite"),
        ("192.168.1.1", "privada clase C"),
        ("fd00::1", "privada IPv6"),
        ("169.254.1.1", "link-local"),
        ("fe80::1", "link-local IPv6"),
        ("100.64.0.1", "CGNAT"),
        ("0.0.0.0", "no especificada"),  # noqa: S104 - dato de prueba, no un bind
        ("240.0.0.1", "reservada"),
        ("224.0.0.1", "multicast"),
        ("ff02::1", "multicast IPv6"),
        ("198.18.0.1", "benchmarking"),
    ],
)
async def test_blocked_networks_are_rejected(address: str, label: str) -> None:
    with pytest.raises(BlockedTargetError) as excinfo:
        await guard(address).validate("https://interno.test")
    assert excinfo.value.reason == "blocked_network", label


async def test_metadata_address_is_rejected() -> None:
    with pytest.raises(BlockedTargetError) as excinfo:
        await guard("169.254.169.254").validate("https://cualquier-cosa.test")
    assert excinfo.value.reason in {"metadata_endpoint", "blocked_network"}


@pytest.mark.parametrize("host", ["metadata.google.internal", "metadata.goog", "instance-data"])
async def test_metadata_hostnames_are_rejected_before_resolving(host: str) -> None:
    """Se rechazan por nombre: ni siquiera se emite la consulta DNS."""
    blocked = UrlGuard(GuardPolicy(), resolver=failing_resolver)
    with pytest.raises(BlockedTargetError) as excinfo:
        await blocked.validate(f"http://{host}/computeMetadata/v1/")
    assert excinfo.value.reason == "metadata_endpoint"


async def test_a_single_blocked_address_invalidates_the_host() -> None:
    """DNS con varias respuestas: basta una privada para rechazar el host."""
    with pytest.raises(BlockedTargetError) as excinfo:
        await guard("93.184.216.34", "127.0.0.1").validate("https://mixto.test")
    assert excinfo.value.reason == "blocked_network"


async def test_ipv4_mapped_in_ipv6_is_unwrapped_and_validated() -> None:
    """`::ffff:127.0.0.1` es loopback disfrazado de IPv6."""
    with pytest.raises(BlockedTargetError) as excinfo:
        await guard("::ffff:127.0.0.1").validate("https://disfrazado.test")
    assert excinfo.value.reason == "blocked_network"


async def test_ip_literal_in_the_url_is_validated_too() -> None:
    with pytest.raises(BlockedTargetError) as excinfo:
        await UrlGuard(GuardPolicy(), resolver=failing_resolver).validate("http://192.168.0.1/")
    assert excinfo.value.reason == "blocked_network"


async def test_decimal_encoded_loopback_is_rejected() -> None:
    """`http://2130706433/` es 127.0.0.1 en forma decimal."""
    with pytest.raises(BlockedTargetError):
        await UrlGuard(GuardPolicy(), resolver=failing_resolver).validate("http://2130706433/")


# ── Esquema, puerto y forma ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://interno.test/",
        "ftp://interno.test/",
        "dict://interno.test:11211/",
        "no-es-una-url",
        "",
    ],
)
async def test_non_http_schemes_are_rejected(url: str) -> None:
    with pytest.raises(BlockedTargetError) as excinfo:
        await guard().validate(url)
    assert excinfo.value.reason in {"invalid_url", "scheme_not_allowed"}


async def test_embedded_credentials_are_rejected() -> None:
    with pytest.raises(BlockedTargetError) as excinfo:
        await guard().validate("https://usuario:clave@softree.mx")
    assert excinfo.value.reason == "invalid_url"


async def test_credential_confusion_is_rejected() -> None:
    """`https://softree.mx@interno.test` apunta en realidad a interno.test."""
    with pytest.raises(BlockedTargetError):
        await guard().validate("https://softree.mx@interno.test")


@pytest.mark.parametrize("port", [22, 3306, 5432, 6379, 8080, 11211])
async def test_ports_outside_the_allowlist_are_rejected(port: int) -> None:
    with pytest.raises(BlockedTargetError) as excinfo:
        await guard().validate(f"http://softree.mx:{port}/")
    assert excinfo.value.reason == "port_not_allowed"


async def test_extra_ports_can_be_allowed_explicitly() -> None:
    target = await guard("93.184.216.34", allowed_ports=(80, 443, 8443)).validate(
        "https://softree.mx:8443/"
    )
    assert target.port == 8443


async def test_dns_failure_is_reported_as_such() -> None:
    from softree_audit.services.common import url_guard

    async def broken(host: str, port: int) -> Sequence[str]:
        raise url_guard.BlockedTargetError("sin dns", reason="dns_resolution_failed")

    with pytest.raises(BlockedTargetError) as excinfo:
        await UrlGuard(GuardPolicy(), resolver=broken).validate("https://inexistente.test")
    assert excinfo.value.reason == "dns_resolution_failed"


async def test_host_without_addresses_is_rejected() -> None:
    with pytest.raises(BlockedTargetError) as excinfo:
        await UrlGuard(GuardPolicy(), resolver=resolver_returning()).validate("https://vacio.test")
    assert excinfo.value.reason == "dns_no_addresses"


# ── Excepción de desarrollo ────────────────────────────────────────────────


async def test_private_networks_can_be_allowed_in_development() -> None:
    target = await guard("172.20.0.7", allow_private_networks=True).validate("http://test-target/")
    assert str(target.ip) == "172.20.0.7"


async def test_multicast_stays_blocked_even_in_development() -> None:
    """La excepción de desarrollo no abre destinos que nunca son legítimos."""
    with pytest.raises(BlockedTargetError):
        await guard("224.0.0.1", allow_private_networks=True).validate("http://multicast.test/")


async def test_metadata_stays_blocked_even_in_development() -> None:
    with pytest.raises(BlockedTargetError) as excinfo:
        await guard("169.254.169.254", allow_private_networks=True).validate("http://meta.test/")
    assert excinfo.value.reason == "metadata_endpoint"


# ── Alcance autorizado ─────────────────────────────────────────────────────

SCOPE = ScopePolicy(
    allowed_domains=("softree.mx",),
    allowed_paths=("/blog",),
    excluded_paths=("/blog/privado",),
)


async def test_out_of_scope_domain_is_rejected_before_dns() -> None:
    """No se emite ni la consulta DNS de un destino fuera de alcance."""
    blocked = UrlGuard(GuardPolicy(), resolver=failing_resolver)
    with pytest.raises(BlockedTargetError) as excinfo:
        await blocked.validate("https://otro-dominio.test/blog", scope=SCOPE)
    assert excinfo.value.reason == "out_of_scope"


async def test_path_outside_the_allowed_prefix_is_rejected() -> None:
    with pytest.raises(BlockedTargetError) as excinfo:
        await guard().validate("https://softree.mx/tienda", scope=SCOPE)
    assert excinfo.value.reason == "out_of_scope"


async def test_excluded_path_is_rejected() -> None:
    with pytest.raises(BlockedTargetError) as excinfo:
        await guard().validate("https://softree.mx/blog/privado/x", scope=SCOPE)
    assert excinfo.value.reason == "out_of_scope"


async def test_in_scope_url_is_allowed() -> None:
    target = await guard().validate("https://softree.mx/blog/entrada", scope=SCOPE)
    assert target.url == "https://softree.mx/blog/entrada"


async def test_subdomain_is_in_scope() -> None:
    target = await guard().validate("https://www.softree.mx/blog", scope=SCOPE)
    assert target.host == "www.softree.mx"


async def test_lookalike_domain_is_out_of_scope() -> None:
    with pytest.raises(BlockedTargetError) as excinfo:
        await guard().validate("https://malicioso-softree.mx/blog", scope=SCOPE)
    assert excinfo.value.reason == "out_of_scope"


def test_scope_policy_from_snapshot() -> None:
    policy = ScopePolicy.from_snapshot(
        {
            "allowed_domains": ["softree.mx"],
            "allowed_paths": [],
            "excluded_paths": ["/admin"],
        }
    )
    assert policy.permits("https://softree.mx/") is True
    assert policy.permits("https://softree.mx/admin/panel") is False
    assert policy.permits("https://otro.test/") is False


def test_scope_policy_tolerates_a_malformed_snapshot() -> None:
    """Un snapshot antiguo o incompleto no debe reventar el pipeline."""
    policy = ScopePolicy.from_snapshot({"allowed_domains": "no-es-una-lista"})
    assert policy.allowed_domains == ()
    assert policy.permits("https://softree.mx/") is False


# ── Formas alternativas de IPv4 ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("host", "label"),
    [
        ("2130706433", "decimal de 127.0.0.1"),
        ("0x7f000001", "hexadecimal de 127.0.0.1"),
        ("017700000001", "octal de 127.0.0.1"),
        ("127.1", "forma corta de 127.0.0.1"),
        ("0177.0.0.1", "octal por octeto"),
        ("0x7f.0.0.1", "hexadecimal por octeto"),
        ("3232235777", "decimal de 192.168.1.1"),
        ("2852039166", "decimal de 169.254.169.254"),
    ],
)
async def test_obscured_ipv4_forms_are_resolved_and_blocked(host: str, label: str) -> None:
    """Formas que `inet_aton` interpreta como IP interna, sin pasar por DNS."""
    blocked = UrlGuard(GuardPolicy(), resolver=failing_resolver)
    with pytest.raises(BlockedTargetError) as excinfo:
        await blocked.validate(f"http://{host}/")
    assert excinfo.value.reason in {"blocked_network", "metadata_endpoint"}, label


def test_parse_obscured_ipv4() -> None:
    from softree_audit.services.common.url_guard import parse_obscured_ipv4

    assert str(parse_obscured_ipv4("2130706433")) == "127.0.0.1"
    assert str(parse_obscured_ipv4("127.1")) == "127.0.0.1"
    assert str(parse_obscured_ipv4("0x7f000001")) == "127.0.0.1"
    # Un dominio real nunca debe interpretarse como dirección.
    assert parse_obscured_ipv4("softree.mx") is None
    assert parse_obscured_ipv4("www.softree.mx") is None
    assert parse_obscured_ipv4("") is None
    assert parse_obscured_ipv4("999.999.999.999") is None
    assert parse_obscured_ipv4("4294967296") is None
