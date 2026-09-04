"""Dependencias de FastAPI.

Los recursos compartidos (motor de base de datos, cliente de Redis) viven en
`app.state` y se crean una sola vez en el ciclo de vida de la aplicación.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from softree_audit.auth.service import AuthService
from softree_audit.core.config import Settings
from softree_audit.core.errors import AuthenticationError
from softree_audit.core.rate_limit import RateLimiter
from softree_audit.core.redis import RedisClient
from softree_audit.core.security import decode_token
from softree_audit.models import User

# `auto_error=False` para poder devolver el formato de error propio en lugar
# del de FastAPI.
bearer_scheme = HTTPBearer(auto_error=False, scheme_name="Bearer")


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Sesión por petición: commit al terminar, rollback ante cualquier error."""
    factory = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_redis(request: Request) -> RedisClient:
    redis: RedisClient = request.app.state.redis
    return redis


def get_rate_limiter(redis: Annotated[RedisClient, Depends(get_redis)]) -> RateLimiter:
    return RateLimiter(redis)


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AuthService:
    return AuthService(session, settings)


def client_ip(request: Request) -> str:
    """IP del cliente.

    Se confía en `X-Forwarded-For` únicamente porque el despliegue previsto
    sitúa un reverse proxy propio delante de la API
    (`docs/development/deployment.md`). Sin proxy, `request.client` es la fuente.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError()

    claims = decode_token(
        credentials.credentials,
        secret_key=settings.secret_key,
        expected_type="access",
    )
    return await auth.get_active_user(claims.subject)


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]
