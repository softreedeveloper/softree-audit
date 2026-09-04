"""OAuth con Google (ADR-005, `security.md` §7)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from softree_audit.services.search_console.oauth import (
    AUTH_ENDPOINT,
    SCOPES,
    TOKEN_ENDPOINT,
    OAuthCredentials,
    OAuthError,
    OAuthNotConfiguredError,
    RefreshTokenRevokedError,
    authorization_url,
    exchange_code,
    refresh_access_token,
)

pytestmark = pytest.mark.unit

CREDENTIALS = OAuthCredentials(
    client_id="cliente.apps.googleusercontent.com",
    client_secret="secreto-de-prueba",
    redirect_uri="https://audit.softree.mx/api/v1/integrations/google/callback",
)


def test_authorization_url_contains_the_expected_parameters() -> None:
    url = authorization_url(CREDENTIALS, "estado-aleatorio")
    parts = urlsplit(url)
    params = {key: value[0] for key, value in parse_qs(parts.query).items()}

    assert url.startswith(AUTH_ENDPOINT)
    assert params["client_id"] == CREDENTIALS.client_id
    assert params["redirect_uri"] == CREDENTIALS.redirect_uri
    assert params["response_type"] == "code"
    assert params["state"] == "estado-aleatorio"


@pytest.mark.security
def test_only_read_only_scope_is_requested() -> None:
    """La plataforma nunca modifica la propiedad del cliente."""
    params = parse_qs(urlsplit(authorization_url(CREDENTIALS, "x")).query)
    assert params["scope"][0] == " ".join(SCOPES)
    assert "readonly" in params["scope"][0]


def test_offline_access_is_requested_so_google_returns_a_refresh_token() -> None:
    """Sin `access_type=offline` y `prompt=consent` no llega refresh token."""
    params = parse_qs(urlsplit(authorization_url(CREDENTIALS, "x")).query)
    assert params["access_type"][0] == "offline"
    assert params["prompt"][0] == "consent"


def test_authorization_url_requires_configuration() -> None:
    empty = OAuthCredentials(client_id="", client_secret="", redirect_uri="x")
    with pytest.raises(OAuthNotConfiguredError):
        authorization_url(empty, "x")


@respx.mock
async def test_exchange_code_returns_both_tokens() -> None:
    respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "ya29.acceso",
                "refresh_token": "1//04refresco",
                "expires_in": 3599,
                "scope": " ".join(SCOPES),
                "token_type": "Bearer",
            },
        )
    )
    tokens = await exchange_code(CREDENTIALS, "codigo")
    assert tokens.access_token == "ya29.acceso"
    assert tokens.refresh_token == "1//04refresco"
    assert tokens.expires_in == 3599


@respx.mock
async def test_refresh_returns_a_new_access_token() -> None:
    respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"access_token": "ya29.nuevo", "expires_in": 3599})
    )
    tokens = await refresh_access_token(CREDENTIALS, "1//04refresco")
    assert tokens.access_token == "ya29.nuevo"
    # Google no reenvía el refresh token en cada renovación.
    assert tokens.refresh_token is None


@respx.mock
@pytest.mark.security
async def test_revoked_grant_is_distinguished() -> None:
    """Un acceso revocado exige reconectar, no reintentar."""
    respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )
    with pytest.raises(RefreshTokenRevokedError) as excinfo:
        await refresh_access_token(CREDENTIALS, "1//04caducado")
    assert excinfo.value.reason == "invalid_grant"


@respx.mock
async def test_other_oauth_errors_keep_their_code() -> None:
    respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(401, json={"error": "invalid_client"})
    )
    with pytest.raises(OAuthError) as excinfo:
        await exchange_code(CREDENTIALS, "codigo")
    assert excinfo.value.reason == "invalid_client"


@respx.mock
async def test_network_failure_is_retried_then_reported() -> None:
    route = respx.post(TOKEN_ENDPOINT).mock(side_effect=httpx.ConnectError("sin red"))
    with pytest.raises(OAuthError) as excinfo:
        await exchange_code(CREDENTIALS, "codigo")
    assert excinfo.value.reason == "unreachable"
    assert route.call_count == 3


@respx.mock
async def test_response_without_access_token_is_rejected() -> None:
    respx.post(TOKEN_ENDPOINT).mock(return_value=httpx.Response(200, json={"expires_in": 10}))
    with pytest.raises(OAuthError) as excinfo:
        await exchange_code(CREDENTIALS, "codigo")
    assert excinfo.value.reason == "invalid_response"
