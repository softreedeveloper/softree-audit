"""Endpoints de autenticación.

El access token viaja en `Authorization: Bearer`; el refresh token en una cookie
`HttpOnly` restringida a `/api/v1/auth` (ADR-008).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from softree_audit.api.deps import (
    AppSettings,
    CurrentUser,
    Limiter,
    client_ip,
    get_auth_service,
)
from softree_audit.auth.service import AuthService, SessionPair
from softree_audit.core import rate_limit
from softree_audit.core.config import Settings
from softree_audit.core.errors import InvalidTokenError
from softree_audit.core.security import decode_token
from softree_audit.schemas.auth import LoginRequest, TokenResponse, UserRead
from softree_audit.schemas.common import ErrorResponse

router = APIRouter(prefix="/auth", tags=["auth"])

AuthDep = Annotated[AuthService, Depends(get_auth_service)]
ClientIp = Annotated[str, Depends(client_ip)]

REFRESH_COOKIE_PATH = "/api/v1/auth"


def _refresh_identity(token: str | None, settings: Settings, ip: str) -> str:
    """Sujeto del límite de tasa para `/auth/refresh`."""
    if token:
        try:
            claims = decode_token(token, secret_key=settings.secret_key, expected_type="refresh")
        except InvalidTokenError:
            return f"ip:{ip}"
        else:
            return f"user:{claims.subject}"
    return f"ip:{ip}"


def _set_refresh_cookie(response: Response, settings: Settings, pair: SessionPair) -> None:
    """Fija la cookie de refresh.

    `Path` restringido a los endpoints de autenticación: ningún otro endpoint
    recibe la cookie, por lo que la API de negocio no tiene superficie CSRF
    (ADR-008).
    """
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=pair.refresh.token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        path=REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path=REFRESH_COOKIE_PATH,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión",
    responses={
        401: {"model": ErrorResponse, "description": "Credenciales inválidas"},
        429: {"model": ErrorResponse, "description": "Demasiados intentos"},
    },
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthDep,
    settings: AppSettings,
    limiter: Limiter,
    ip: ClientIp,
) -> TokenResponse:
    await limiter.check(rate_limit.LOGIN, ip)

    user = await auth.authenticate(payload.email, payload.password)
    pair = await auth.issue_session(
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=ip,
    )

    # Un login exitoso limpia el contador para no castigar al usuario legítimo.
    await limiter.reset(rate_limit.LOGIN, ip)
    _set_refresh_cookie(response, settings, pair)

    return TokenResponse(
        access_token=pair.access.token,
        expires_in=settings.access_token_ttl_minutes * 60,
        user=UserRead.model_validate(user),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Renovar el access token",
    responses={401: {"model": ErrorResponse, "description": "Refresh token inválido"}},
)
async def refresh(
    request: Request,
    response: Response,
    auth: AuthDep,
    settings: AppSettings,
    limiter: Limiter,
    ip: ClientIp,
) -> TokenResponse:
    token = request.cookies.get(settings.refresh_cookie_name)
    # El límite se aplica por usuario cuando el token es legible, y por IP en
    # caso contrario. Limitar solo por IP dejaría que varios usuarios detrás de
    # un mismo proxy se expulsaran entre sí, y no protege más: un refresh token
    # es un JWT firmado, no algo que se pueda adivinar por fuerza bruta.
    await limiter.check(rate_limit.REFRESH, _refresh_identity(token, settings, ip))

    if not token:
        raise InvalidTokenError()

    try:
        pair = await auth.rotate_session(
            token,
            user_agent=request.headers.get("user-agent"),
            ip_address=ip,
        )
    except InvalidTokenError:
        # La cookie ya no sirve: se borra para que el cliente no reintente.
        _clear_refresh_cookie(response, settings)
        raise

    _set_refresh_cookie(response, settings, pair)
    return TokenResponse(
        access_token=pair.access.token,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesión",
)
async def logout(
    request: Request,
    response: Response,
    auth: AuthDep,
    settings: AppSettings,
) -> None:
    # Idempotente: sin cookie o con una cookie ilegible, la sesión ya no existe.
    await auth.logout(request.cookies.get(settings.refresh_cookie_name))
    _clear_refresh_cookie(response, settings)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Usuario autenticado",
    responses={401: {"model": ErrorResponse, "description": "No autenticado"}},
)
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
