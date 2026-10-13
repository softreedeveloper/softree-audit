"""Origen público de la plataforma.

Frontend y API comparten dominio (ADR-008), así que la URL de vuelta tras el
consentimiento de Google y el URI de callback se pueden deducir de la propia
petición. `APP_URL` y `GOOGLE_REDIRECT_URI` existen solo como anulación.
"""

from __future__ import annotations

from softree_audit.core.config import Settings

DEFAULT_ORIGIN = "http://localhost:4321"
GOOGLE_CALLBACK_PATH = "/integrations/google/callback"


def public_origin(settings: Settings, *, host: str | None, scheme: str | None) -> str:
    """`https://audit.softree.mx`, sin barra final.

    `host` y `scheme` vienen de `X-Forwarded-Host`/`Host` y
    `X-Forwarded-Proto`, que nginx y Traefik rellenan con los valores de la
    petición original (`docs/development/deployment.md`).
    """
    if settings.app_url:
        return settings.app_url.rstrip("/")
    if not host:
        return DEFAULT_ORIGIN
    proto = (scheme or "http").split(",")[0].strip().lower() or "http"
    return f"{proto}://{host.split(',')[0].strip()}"


def google_redirect_uri(settings: Settings, origin: str) -> str:
    """URI de callback que se envía a Google y que debe estar registrado allí."""
    if settings.google_redirect_uri:
        return settings.google_redirect_uri
    return f"{origin}{settings.api_prefix}{GOOGLE_CALLBACK_PATH}"
