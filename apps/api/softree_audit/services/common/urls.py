"""Normalización y validación de URL y de nombres de host.

Este módulo solo se ocupa de la *forma* de una URL. La validación de red
(resolución DNS, rangos bloqueados, redirects) vive en el guard de SSRF, que se
implementa en el Slice 3 y es el único punto autorizado para emitir tráfico
hacia un target (`docs/spec/security.md` §2).
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})
DEFAULT_PORTS = {"http": 80, "https": 443}

MAX_URL_LENGTH = 2048
MAX_HOSTNAME_LENGTH = 253
MAX_PATH_LENGTH = 1024

# Etiqueta de nombre de host: alfanumérica, con guiones internos.
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


class InvalidUrlError(ValueError):
    """La URL no tiene una forma aceptable."""


class InvalidHostnameError(ValueError):
    """El nombre de host no tiene una forma aceptable."""


class InvalidPathError(ValueError):
    """La ruta no tiene una forma aceptable."""


def normalize_hostname(value: str) -> str:
    """Devuelve el host en minúsculas y validado.

    Acepta nombres de dominio y direcciones IP literales. No acepta esquema,
    puerto, ruta ni credenciales.
    """
    host = value.strip().lower().rstrip(".")
    if not host:
        raise InvalidHostnameError("El host no puede estar vacío")
    if len(host) > MAX_HOSTNAME_LENGTH:
        raise InvalidHostnameError(f"El host supera {MAX_HOSTNAME_LENGTH} caracteres")
    if any(char in host for char in "/\\?#@ \t\n\r"):
        raise InvalidHostnameError("El host contiene caracteres no permitidos")

    # Dirección IPv6 entre corchetes.
    if host.startswith("[") and host.endswith("]"):
        try:
            ipaddress.IPv6Address(host[1:-1])
        except ValueError as exc:
            raise InvalidHostnameError("Dirección IPv6 inválida") from exc
        return host

    try:
        # Una IP literal es un host válido; se normaliza a su forma canónica.
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass

    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise InvalidHostnameError("El host no es un nombre de dominio válido") from exc

    labels = host.split(".")
    if any(not _LABEL.match(label) for label in labels):
        raise InvalidHostnameError("El host no es un nombre de dominio válido")
    return host


def normalize_path(value: str) -> str:
    """Valida una ruta de scope.

    Las rutas se comparan por prefijo, por lo que no se aceptan comodines
    (`docs/spec/security.md` §12). `/` significa «todo el sitio».
    """
    path = value.strip()
    if not path.startswith("/"):
        raise InvalidPathError("La ruta debe comenzar con /")
    if len(path) > MAX_PATH_LENGTH:
        raise InvalidPathError(f"La ruta supera {MAX_PATH_LENGTH} caracteres")
    if any(char in path for char in " \t\n\r"):
        raise InvalidPathError("La ruta no puede contener espacios")
    if "*" in path or "?" in path:
        raise InvalidPathError("La ruta no admite comodines; la comparación es por prefijo")
    if ".." in path:
        raise InvalidPathError("La ruta no puede contener '..'")
    # `/a/` y `/a` deben tratarse igual.
    return path.rstrip("/") or "/"


def normalize_url(value: str) -> str:
    """Normaliza la URL base de un sitio.

    - Solo `http` y `https`.
    - Rechaza credenciales embebidas.
    - Host en minúsculas, puerto por defecto eliminado.
    - Fragmento y consulta eliminados: la URL base identifica un sitio.
    """
    raw = value.strip()
    if not raw:
        raise InvalidUrlError("La URL no puede estar vacía")
    if len(raw) > MAX_URL_LENGTH:
        raise InvalidUrlError(f"La URL supera {MAX_URL_LENGTH} caracteres")
    if any(char in raw for char in " \t\n\r"):
        raise InvalidUrlError("La URL no puede contener espacios")

    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise InvalidUrlError("La URL debe usar http o https")
    if parts.username or parts.password:
        raise InvalidUrlError("La URL no puede incluir credenciales")
    if not parts.hostname:
        raise InvalidUrlError("La URL no incluye un host")

    host = normalize_hostname(parts.hostname)

    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidUrlError("El puerto de la URL no es válido") from exc
    netloc = host if port in (None, DEFAULT_PORTS[scheme]) else f"{host}:{port}"

    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def hostname_of(url: str) -> str:
    """Host normalizado de una URL ya validada."""
    hostname = urlsplit(url).hostname
    if hostname is None:
        raise InvalidUrlError("La URL no incluye un host")
    return normalize_hostname(hostname)


def matches_domain(host: str, allowed_domain: str) -> bool:
    """Comprueba si `host` pertenece a `allowed_domain`.

    Coincide el dominio exacto y sus subdominios. `ejemplo.com` cubre
    `www.ejemplo.com`, pero nunca `malicioso-ejemplo.com`.
    """
    host = host.lower()
    allowed_domain = allowed_domain.lower()
    return host == allowed_domain or host.endswith(f".{allowed_domain}")


def matches_path(path: str, prefix: str) -> bool:
    """Comparación por prefijo respetando los límites de segmento."""
    if prefix == "/":
        return True
    normalized = path.rstrip("/") or "/"
    return normalized == prefix or normalized.startswith(f"{prefix}/")
