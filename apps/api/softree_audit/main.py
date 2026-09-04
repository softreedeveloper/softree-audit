"""Aplicación FastAPI de Softree Audit."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.exceptions import HTTPException as StarletteHTTPException

from softree_audit.api.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from softree_audit.api.v1.router import api_router
from softree_audit.core.config import Settings, get_settings
from softree_audit.core.errors import AppError
from softree_audit.core.logging import configure_logging, get_logger
from softree_audit.db.session import create_engine, create_session_factory
from softree_audit.scans.queue import create_queue
from softree_audit.version import APP_VERSION

logger = get_logger(__name__)

DESCRIPTION = """
API interna de **Softree Audit**: auditoría de seguridad, SEO y rendimiento de
sitios web propios, entregados por Softree o autorizados explícitamente por el
cliente.

Autenticación mediante `Authorization: Bearer <access_token>` obtenido en
`POST /api/v1/auth/login`.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Crea y libera los recursos compartidos una sola vez."""
    settings: Settings = app.state.settings

    engine = create_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.queue = await create_queue(settings)

    logger.info(
        "app.startup",
        environment=settings.app_env,
        app_version=APP_VERSION,
        ssrf_allow_private_networks=settings.ssrf_allow_private_networks,
    )
    try:
        yield
    finally:
        await app.state.queue.aclose()
        await app.state.redis.aclose()
        await engine.dispose()
        logger.info("app.shutdown")


def _register_exception_handlers(app: FastAPI) -> None:
    """Formato único de error para toda la API (`docs/spec/api.md`)."""

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_payload(),
            headers=exc.headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Los datos enviados no son válidos.",
                    "details": [
                        {
                            "field": ".".join(str(part) for part in error["loc"][1:]),
                            "message": error["msg"],
                            "type": error["type"],
                        }
                        for error in exc.errors()
                    ],
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            401: "unauthenticated",
            403: "permission_denied",
            404: "not_found",
            405: "method_not_allowed",
        }.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": str(exc.detail),
                    "details": None,
                }
            },
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        # No se filtra el detalle interno al cliente, pero sí queda en el log.
        logger.exception("app.unhandled_exception", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Ocurrió un error inesperado.",
                    "details": None,
                }
            },
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    # La documentación interactiva queda deshabilitada en producción: es una
    # herramienta interna y no necesita estar expuesta.
    docs_url = None if settings.is_production else f"{settings.api_prefix}/docs"
    redoc_url = None if settings.is_production else f"{settings.api_prefix}/redoc"

    app = FastAPI(
        title="Softree Audit API",
        description=DESCRIPTION,
        version=APP_VERSION,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestContextMiddleware)

    # Sin orígenes configurados no se registra CORS: el despliegue previsto es
    # same-origin (D-005).
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID", "X-App-Version"],
            max_age=600,
        )

    _register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
