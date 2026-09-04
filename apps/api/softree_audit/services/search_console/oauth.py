"""OAuth 2.0 con Google (ADR-005).

Solo se persiste el refresh token, cifrado. El access token se obtiene en
memoria en cada uso y nunca toca la base de datos
(`docs/spec/security.md` §7).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from softree_audit.core.logging import get_logger
from softree_audit.services.common.retry import with_retry

logger = get_logger(__name__)

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105 - URL pública, no un secreto

# Solo lectura: la plataforma nunca modifica la propiedad del cliente.
SCOPES = ("https://www.googleapis.com/auth/webmasters.readonly",)

TRANSIENT_ERRORS = (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError)


class OAuthError(Exception):
    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class RefreshTokenRevokedError(OAuthError):
    """El usuario retiró el acceso o la credencial caducó."""

    def __init__(self, message: str = "El acceso a Google fue revocado.") -> None:
        super().__init__(message, reason="invalid_grant")


class OAuthNotConfiguredError(OAuthError):
    def __init__(self) -> None:
        super().__init__(
            "La integración con Google no está configurada: faltan GOOGLE_CLIENT_ID y "
            "GOOGLE_CLIENT_SECRET.",
            reason="not_configured",
        )


@dataclass(frozen=True, slots=True)
class OAuthCredentials:
    client_id: str
    client_secret: str
    redirect_uri: str

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


@dataclass(frozen=True, slots=True)
class TokenBundle:
    access_token: str
    expires_in: int
    refresh_token: str | None = None
    scope: str | None = None


def authorization_url(credentials: OAuthCredentials, state: str) -> str:
    """URL de consentimiento.

    `access_type=offline` y `prompt=consent` garantizan que Google devuelva un
    refresh token; sin ellos, una reconexión del mismo usuario no lo incluye y
    la conexión quedaría inservible al expirar el access token.
    """
    if not credentials.is_configured:
        raise OAuthNotConfiguredError()

    params = {
        "client_id": credentials.client_id,
        "redirect_uri": credentials.redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


async def exchange_code(
    credentials: OAuthCredentials, code: str, *, timeout_seconds: float = 30.0
) -> TokenBundle:
    """Canjea el código de autorización por tokens."""
    payload = {
        "code": code,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "redirect_uri": credentials.redirect_uri,
        "grant_type": "authorization_code",
    }
    return await _token_request(payload, timeout_seconds=timeout_seconds)


async def refresh_access_token(
    credentials: OAuthCredentials, refresh_token: str, *, timeout_seconds: float = 30.0
) -> TokenBundle:
    """Obtiene un access token nuevo. Nunca se persiste."""
    payload = {
        "refresh_token": refresh_token,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "grant_type": "refresh_token",
    }
    return await _token_request(payload, timeout_seconds=timeout_seconds)


async def _token_request(payload: dict[str, str], *, timeout_seconds: float) -> TokenBundle:
    async def call() -> httpx.Response:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds), trust_env=False
        ) as client:
            return await client.post(TOKEN_ENDPOINT, data=payload)

    try:
        response = await with_retry(
            call, retry_on=TRANSIENT_ERRORS, attempts=3, name="google-oauth"
        )
    except TRANSIENT_ERRORS as exc:
        raise OAuthError(
            f"No fue posible contactar con Google: {exc}", reason="unreachable"
        ) from exc

    if response.status_code >= 400:
        error = _error_code(response)
        if error == "invalid_grant":
            raise RefreshTokenRevokedError()
        # El cuerpo puede contener el client_secret reflejado: no se registra.
        logger.warning("google_oauth.token_error", status=response.status_code, error=error)
        raise OAuthError(
            f"Google rechazó la petición de token ({error}).", reason=error or "token_error"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise OAuthError(
            "Respuesta no interpretable de Google.", reason="invalid_response"
        ) from exc

    access_token = data.get("access_token")
    if not access_token:
        raise OAuthError("Google no devolvió un access token.", reason="invalid_response")

    return TokenBundle(
        access_token=str(access_token),
        expires_in=int(data.get("expires_in", 3600)),
        refresh_token=data.get("refresh_token"),
        scope=data.get("scope"),
    )


def _error_code(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    if isinstance(data, dict):
        value = data.get("error")
        return str(value) if value else None
    return None
