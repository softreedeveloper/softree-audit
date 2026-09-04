"""Guard de SSRF: único punto autorizado para validar un destino externo.

Implementa la secuencia obligatoria de `docs/spec/security.md` §2. Ningún módulo
del pipeline debe emitir tráfico hacia un host controlado por el usuario sin
pasar por aquí, y la validación se repite en **cada** salto de redirección.

El módulo no hace peticiones: solo resuelve y decide. La emisión vive en
`http_client.py`, que fija la IP validada para cerrar la ventana de DNS
rebinding.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

from softree_audit.services.common.urls import (
    ALLOWED_SCHEMES,
    DEFAULT_PORTS,
    InvalidHostnameError,
    InvalidUrlError,
    matches_domain,
    matches_path,
    normalize_hostname,
    normalize_url,
)

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Rangos bloqueados (`docs/spec/security.md` §2). Se comprueban sobre cada
# dirección resuelta, no sobre el nombre.
BLOCKED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        # Loopback
        "127.0.0.0/8",
        "::1/128",
        # Redes privadas
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "fc00::/7",
        # Link-local
        "169.254.0.0/16",
        "fe80::/10",
        # CGNAT
        "100.64.0.0/10",
        # Reservadas y de uso especial
        "0.0.0.0/8",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "240.0.0.0/4",
        "255.255.255.255/32",
        "::/128",
        "2001:db8::/32",
        # Multicast
        "224.0.0.0/4",
        "ff00::/8",
    )
)

# Endpoints de metadatos de nube, bloqueados también por nombre.
BLOCKED_HOSTNAMES = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
        "instance-data",
        "instance-data.ec2.internal",
    }
)
BLOCKED_ADDRESSES = frozenset({"169.254.169.254", "100.100.100.200", "fd00:ec2::254"})

MAX_REDIRECTS = 5


class BlockedTargetError(Exception):
    """El destino no puede alcanzarse. `reason` es un código estable para el log."""

    def __init__(self, message: str, *, reason: str, url: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.url = url


class Resolver(Protocol):
    """Resolución de nombres. Se inyecta para poder probar sin red."""

    async def __call__(self, host: str, port: int) -> Sequence[str]: ...


async def system_resolver(host: str, port: int) -> Sequence[str]:
    """Resolución con `getaddrinfo`, cubriendo IPv4 e IPv6."""
    import asyncio

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise BlockedTargetError(
            f"No fue posible resolver «{host}».", reason="dns_resolution_failed"
        ) from exc
    # `sockaddr` es (host, port) en IPv4 y (host, port, flowinfo, scopeid) en
    # IPv6; el primer elemento es siempre la dirección.
    return [str(info[4][0]) for info in infos]


def _parse_ipv4_part(part: str) -> int:
    """Interpreta un octeto en decimal, octal o hexadecimal.

    Python 3 no acepta `int("0177", 0)` porque prohíbe el cero inicial, pero
    `inet_aton` sí lo lee como octal, así que hay que reproducir esa semántica.
    """
    lowered = part.lower()
    if lowered.startswith(("0x", "-0x")):
        return int(part, 16)
    if lowered.startswith("0") and len(part) > 1:
        return int(part, 8)
    return int(part, 10)


def parse_obscured_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """Interpreta las formas alternativas de una IPv4 que acepta `inet_aton`.

    `http://2130706433/`, `http://0x7f.1/` o `http://0177.0.0.1/` son
    127.0.0.1 para la resolución del sistema, pero `ipaddress.ip_address` los
    rechaza y quedarían como si fueran nombres de dominio. Reconocerlos aquí
    evita que una IP interna se cuele disfrazada de host.

    Devuelve `None` si el texto no es una IPv4 en ninguna de esas formas.
    """
    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return None

    values: list[int] = []
    for part in parts:
        if not part:
            return None
        try:
            values.append(_parse_ipv4_part(part))
        except ValueError:
            return None
        if values[-1] < 0:
            return None

    # Semántica de inet_aton: la última parte absorbe los octetos restantes.
    shifts = [24, 16, 8, 0]
    total = 0
    for index, value in enumerate(values[:-1]):
        if value > 0xFF:
            return None
        total |= value << shifts[index]

    remaining_bits = 8 * (4 - (len(values) - 1))
    last = values[-1]
    if last >= 1 << remaining_bits:
        return None
    total |= last

    try:
        return ipaddress.IPv4Address(total)
    except ipaddress.AddressValueError:
        return None


@dataclass(frozen=True, slots=True)
class ScopePolicy:
    """Alcance autorizado, tomado del `scope_snapshot` del scan."""

    allowed_domains: tuple[str, ...]
    allowed_paths: tuple[str, ...] = ()
    excluded_paths: tuple[str, ...] = ()

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, object]) -> ScopePolicy:
        def strings(key: str) -> tuple[str, ...]:
            value = snapshot.get(key) or []
            if not isinstance(value, list):
                return ()
            return tuple(str(item) for item in value)

        return cls(
            allowed_domains=strings("allowed_domains"),
            allowed_paths=strings("allowed_paths"),
            excluded_paths=strings("excluded_paths"),
        )

    def permits(self, url: str) -> bool:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if not any(matches_domain(host, domain) for domain in self.allowed_domains):
            return False

        path = parts.path or "/"
        if any(matches_path(path, prefix) for prefix in self.excluded_paths):
            return False
        return not (
            self.allowed_paths
            and not any(matches_path(path, prefix) for prefix in self.allowed_paths)
        )


@dataclass(frozen=True, slots=True)
class GuardPolicy:
    """Parámetros de red del guard."""

    allowed_ports: tuple[int, ...] = (80, 443)
    # Solo para desarrollo, con el `test-target` en la red de Docker.
    allow_private_networks: bool = False
    max_redirects: int = MAX_REDIRECTS


@dataclass(frozen=True, slots=True)
class ValidatedTarget:
    """Destino aprobado y la IP concreta a la que debe conectarse."""

    url: str
    scheme: str
    host: str
    port: int
    ip: IpAddress
    all_ips: tuple[IpAddress, ...] = field(default=())

    @property
    def pinned_host(self) -> str:
        """Representación del literal IP apta para una URL."""
        return f"[{self.ip}]" if self.ip.version == 6 else str(self.ip)


class UrlGuard:
    """Valida un destino antes de cada petición."""

    def __init__(
        self,
        policy: GuardPolicy | None = None,
        resolver: Resolver | None = None,
    ) -> None:
        self._policy = policy or GuardPolicy()
        self._resolve: Resolver = resolver or system_resolver

    @property
    def policy(self) -> GuardPolicy:
        return self._policy

    async def validate(self, url: str, *, scope: ScopePolicy | None = None) -> ValidatedTarget:
        """Ejecuta la secuencia completa de `security.md` §2.

        Lanza `BlockedTargetError` con un `reason` estable si el destino no es
        alcanzable.
        """
        # 1-5. Forma de la URL, esquema, credenciales, puerto y host.
        try:
            normalized = normalize_url(url)
        except InvalidUrlError as exc:
            raise BlockedTargetError(str(exc), reason="invalid_url", url=url) from exc

        parts = urlsplit(normalized)
        scheme = parts.scheme
        if scheme not in ALLOWED_SCHEMES:
            raise BlockedTargetError(
                "Solo se permiten http y https.", reason="scheme_not_allowed", url=normalized
            )

        try:
            host = normalize_hostname(parts.hostname or "")
        except InvalidHostnameError as exc:
            raise BlockedTargetError(str(exc), reason="invalid_hostname", url=normalized) from exc

        if host in BLOCKED_HOSTNAMES:
            raise BlockedTargetError(
                "El host corresponde a un endpoint de metadatos.",
                reason="metadata_endpoint",
                url=normalized,
            )

        port = parts.port or DEFAULT_PORTS[scheme]
        if port not in self._policy.allowed_ports:
            raise BlockedTargetError(
                f"El puerto {port} no está permitido.", reason="port_not_allowed", url=normalized
            )

        # 8. Alcance autorizado. Se comprueba antes de resolver para no emitir
        #    ni siquiera una consulta DNS hacia un destino fuera de scope.
        if scope is not None and not scope.permits(normalized):
            raise BlockedTargetError(
                "El destino está fuera del alcance autorizado.",
                reason="out_of_scope",
                url=normalized,
            )

        # 6-7. Resolución y validación de todas las direcciones.
        addresses = await self._resolved_addresses(host, port, normalized)
        for address in addresses:
            self._assert_address_allowed(address, normalized)

        return ValidatedTarget(
            url=normalized,
            scheme=scheme,
            host=host,
            port=port,
            ip=addresses[0],
            all_ips=tuple(addresses),
        )

    async def _resolved_addresses(self, host: str, port: int, url: str) -> list[IpAddress]:
        # Un literal IP no necesita resolución, pero sí validación.
        literal = host[1:-1] if host.startswith("[") and host.endswith("]") else host
        try:
            return [ipaddress.ip_address(literal)]
        except ValueError:
            pass

        # Formas alternativas de IPv4 (decimal, octal, hexadecimal), que la
        # resolución del sistema sí interpretaría como direcciones.
        obscured = parse_obscured_ipv4(literal)
        if obscured is not None:
            return [obscured]

        raw = await self._resolve(host, port)
        addresses: list[IpAddress] = []
        for item in raw:
            try:
                addresses.append(ipaddress.ip_address(item))
            except ValueError:
                continue
        if not addresses:
            raise BlockedTargetError(
                f"«{host}» no resolvió a ninguna dirección utilizable.",
                reason="dns_no_addresses",
                url=url,
            )
        return addresses

    def _assert_address_allowed(self, address: IpAddress, url: str) -> None:
        # Una IPv4 envuelta en IPv6 debe validarse como IPv4.
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped

        if str(address) in BLOCKED_ADDRESSES:
            raise BlockedTargetError(
                "La dirección corresponde a un endpoint de metadatos.",
                reason="metadata_endpoint",
                url=url,
            )

        if self._policy.allow_private_networks:
            # Excepción de desarrollo: se mantienen bloqueados los metadatos y
            # el multicast, que nunca son un target legítimo.
            if address.is_multicast:
                raise BlockedTargetError("Dirección multicast.", reason="blocked_network", url=url)
            return

        for network in BLOCKED_NETWORKS:
            if address.version == network.version and address in network:
                raise BlockedTargetError(
                    f"La dirección {address} pertenece a un rango bloqueado ({network}).",
                    reason="blocked_network",
                    url=url,
                )
