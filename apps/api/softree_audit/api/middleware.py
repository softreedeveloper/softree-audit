"""Middlewares propios: identificador de petición y cabeceras de seguridad."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from softree_audit.core.config import Settings
from softree_audit.core.logging import get_logger
from softree_audit.version import APP_VERSION

logger = get_logger("http")

REQUEST_ID_HEADER = "X-Request-ID"

# Rutas de documentación interactiva, con CSP propia.
DOCS_PATHS = frozenset({"/api/v1/docs", "/api/v1/redoc", "/api/v1/docs/oauth2-redirect"})


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Asigna un `X-Request-ID` y registra cada petición."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.exception(
                "http.request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
            )
            structlog.contextvars.clear_contextvars()
            raise

        duration_ms = int((time.perf_counter() - started) * 1000)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers["X-App-Version"] = APP_VERSION
        logger.info(
            "http.request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        structlog.contextvars.clear_contextvars()
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Cabeceras de seguridad de la propia aplicación (`security.md` §11)."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")

        # La API solo devuelve JSON: una CSP mínima es suficiente y evita que
        # una respuesta reflejada se interprete como documento.
        #
        # Excepción: la documentación interactiva carga Swagger UI desde un CDN,
        # por lo que necesita una política propia. Solo está habilitada fuera de
        # producción (ver `create_app`).
        if request.url.path in DOCS_PATHS:
            headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; "
                "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
                "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
                "img-src 'self' https://fastapi.tiangolo.com data:; "
                "connect-src 'self'; font-src 'self' https://cdn.jsdelivr.net; "
                "frame-ancestors 'none'; base-uri 'none'",
            )
        else:
            headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )

        if self._settings.is_production:
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
