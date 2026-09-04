"""Endpoint de salud.

Expone las tres versiones y el valor efectivo de la bandera de SSRF, para que
una configuración peligrosa quede a la vista (`security.md` §2).
"""

from __future__ import annotations

from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Response
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from softree_audit.api.deps import AppSettings, DbSession, get_redis
from softree_audit.core.redis import RedisClient
from softree_audit.schemas.common import HealthResponse
from softree_audit.version import APP_VERSION, REPORT_VERSION, SCAN_ENGINE_VERSION

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Estado del servicio")
async def health(
    response: Response,
    session: DbSession,
    settings: AppSettings,
    redis: Annotated[RedisClient, Depends(get_redis)],
) -> HealthResponse:
    database = "ok"
    try:
        await session.execute(sa.text("SELECT 1"))
    except SQLAlchemyError:
        database = "unavailable"
        # Sin el rollback la sesión queda en estado inconsistente y el commit
        # posterior de la dependencia fallaría, convirtiendo un 503 en un 500.
        await session.rollback()

    redis_status = "ok"
    try:
        await redis.ping()
    except RedisError:
        redis_status = "unavailable"

    status = "ok" if database == "ok" and redis_status == "ok" else "degraded"
    if status != "ok":
        response.status_code = 503

    return HealthResponse(
        status=status,
        environment=settings.app_env,
        app_version=APP_VERSION,
        scan_engine_version=SCAN_ENGINE_VERSION,
        report_version=REPORT_VERSION,
        database=database,
        redis=redis_status,
        ssrf_allow_private_networks=settings.ssrf_allow_private_networks,
    )
