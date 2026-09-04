"""Endpoints de auditorías."""

from __future__ import annotations

import uuid
from typing import Annotated

import sqlalchemy as sa
from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from softree_audit.api.deps import AppSettings, CurrentUser, DbSession, Limiter, client_ip
from softree_audit.comparison.service import ComparisonService
from softree_audit.core import rate_limit
from softree_audit.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from softree_audit.core.redis import RedisClient
from softree_audit.findings.service import FindingService
from softree_audit.models import ScanModuleRun, SearchConsoleMetric
from softree_audit.models.enums import (
    FindingCategory,
    FindingSource,
    FindingStatus,
    ModuleName,
    ScanStatus,
    SearchConsoleDimension,
    SearchConsolePeriod,
    Severity,
)
from softree_audit.scans.queue import enqueue_scan
from softree_audit.scans.service import ScanService
from softree_audit.schemas.common import ErrorResponse, Page
from softree_audit.schemas.comparison import ComparisonResponse
from softree_audit.schemas.finding import FindingRead, ScanScoresResponse, SeverityCounts
from softree_audit.schemas.integration import (
    ScanSearchConsoleResponse,
    SearchConsoleMetricRead,
)
from softree_audit.schemas.scan import (
    PageRead,
    ScanCreate,
    ScanDetail,
    ScanModuleRead,
    ScanRead,
)

router = APIRouter(prefix="/scans", tags=["scans"])

NOT_FOUND: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "La auditoría no existe"}
}

# Clave de idempotencia para el consumo desde n8n (`docs/spec/api.md`).
IDEMPOTENCY_TTL_SECONDS = 24 * 3600


def get_redis_client(request: Request) -> RedisClient:
    redis: RedisClient = request.app.state.redis
    return redis


def get_queue(request: Request) -> ArqRedis:
    queue: ArqRedis = request.app.state.queue
    return queue


def get_service(
    session: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    redis: Annotated[RedisClient, Depends(get_redis_client)],
) -> ScanService:
    return ScanService(session, redis, settings, user.id)


def get_finding_service(session: DbSession, user: CurrentUser) -> FindingService:
    return FindingService(session, user.id)


ServiceDep = Annotated[ScanService, Depends(get_service)]


def get_comparison_service(session: DbSession, user: CurrentUser) -> ComparisonService:
    return ComparisonService(session, user.id)


FindingServiceDep = Annotated[FindingService, Depends(get_finding_service)]
ComparisonServiceDep = Annotated[ComparisonService, Depends(get_comparison_service)]
QueueDep = Annotated[ArqRedis, Depends(get_queue)]
RedisDep = Annotated[RedisClient, Depends(get_redis_client)]


@router.post(
    "",
    response_model=ScanDetail,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Lanzar una auditoría",
    responses={
        404: {"model": ErrorResponse, "description": "El sitio no existe"},
        409: {"model": ErrorResponse, "description": "El sitio no está autorizado o está inactivo"},
        422: {"model": ErrorResponse, "description": "El objetivo no puede auditarse"},
        429: {"model": ErrorResponse, "description": "Demasiadas auditorías"},
    },
)
async def create_scan(
    payload: ScanCreate,
    service: ServiceDep,
    queue: QueueDep,
    redis: RedisDep,
    limiter: Limiter,
    user: CurrentUser,
    ip: Annotated[str, Depends(client_ip)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> ScanDetail:
    """Valida y encola. La respuesta no espera al resultado de la auditoría."""
    await limiter.check(rate_limit.SCAN_CREATE, ip)

    cache_key = f"idem:scan:{user.id}:{idempotency_key}" if idempotency_key else None
    if cache_key:
        existing = await redis.get(cache_key)
        if existing:
            return await service.read(uuid.UUID(existing))

    scan = await service.create(payload.site_id, payload.scan_type)
    await enqueue_scan(queue, scan.id)

    if cache_key:
        await redis.set(cache_key, str(scan.id), ex=IDEMPOTENCY_TTL_SECONDS)
    return scan


@router.get("", response_model=Page[ScanRead], summary="Listar auditorías")
async def list_scans(
    service: ServiceDep,
    site_id: uuid.UUID | None = None,
    scan_status: Annotated[ScanStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page[ScanRead]:
    items, next_cursor, total = await service.list(
        site_id=site_id, status=scan_status, limit=limit, cursor=cursor
    )
    return Page[ScanRead](items=items, next_cursor=next_cursor, total=total)


@router.get(
    "/{scan_id}",
    response_model=ScanDetail,
    summary="Estado y detalle de una auditoría",
    responses=NOT_FOUND,
)
async def get_scan(scan_id: uuid.UUID, service: ServiceDep, response: Response) -> ScanDetail:
    scan = await service.read(scan_id)
    # El progreso se consulta por polling cada 2 s; sin caché intermedia.
    response.headers["Cache-Control"] = "no-store"
    return scan


@router.post(
    "/{scan_id}/cancel",
    response_model=ScanDetail,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Cancelar una auditoría",
    responses={
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "La auditoría ya terminó"},
    },
)
async def cancel_scan(scan_id: uuid.UUID, service: ServiceDep) -> ScanDetail:
    return await service.cancel(scan_id)


@router.get(
    "/{scan_id}/modules",
    response_model=list[ScanModuleRead],
    summary="Estado por módulo",
    responses=NOT_FOUND,
)
async def scan_modules(scan_id: uuid.UUID, service: ServiceDep) -> list[ScanModuleRead]:
    return await service.modules(scan_id)


@router.get(
    "/{scan_id}/pages",
    response_model=Page[PageRead],
    summary="Páginas rastreadas",
    responses=NOT_FOUND,
)
async def scan_pages(
    scan_id: uuid.UUID,
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page[PageRead]:
    items, next_cursor, total = await service.pages(scan_id, limit=limit, cursor=cursor)
    return Page[PageRead](items=items, next_cursor=next_cursor, total=total)


@router.get(
    "/{scan_id}/findings",
    response_model=Page[FindingRead],
    summary="Hallazgos de una auditoría",
    responses=NOT_FOUND,
)
async def scan_findings(
    scan_id: uuid.UUID,
    service: ServiceDep,
    findings: FindingServiceDep,
    severity: Severity | None = None,
    source: FindingSource | None = None,
    category: FindingCategory | None = None,
    status: FindingStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page[FindingRead]:
    # Comprobar la pertenencia del scan antes de leer sus hallazgos.
    await service.get(scan_id)
    items, next_cursor, total = await findings.list(
        scan_id=scan_id,
        severity=severity,
        source=source,
        category=category,
        status=status,
        limit=limit,
        cursor=cursor,
    )
    return Page[FindingRead](items=items, next_cursor=next_cursor, total=total)


@router.get(
    "/{scan_id}/severity-counts",
    response_model=SeverityCounts,
    summary="Hallazgos abiertos por severidad",
    responses=NOT_FOUND,
)
async def scan_severity_counts(
    scan_id: uuid.UUID, service: ServiceDep, findings: FindingServiceDep
) -> SeverityCounts:
    await service.get(scan_id)
    return await findings.severity_counts(scan_id=scan_id)


@router.get(
    "/{scan_id}/search-console",
    response_model=ScanSearchConsoleResponse,
    summary="Métricas de Search Console de la auditoría",
    responses=NOT_FOUND,
)
async def scan_search_console(
    scan_id: uuid.UUID,
    service: ServiceDep,
    session: DbSession,
    period: SearchConsolePeriod = SearchConsolePeriod.LAST_28_DAYS,
    dimension: SearchConsoleDimension = SearchConsoleDimension.QUERY,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> ScanSearchConsoleResponse:
    """Las métricas se filtran siempre por el scan, que pertenece al usuario."""
    scan = await service.get(scan_id)

    module = (
        await session.execute(
            sa.select(ScanModuleRun).where(
                ScanModuleRun.scan_id == scan_id,
                ScanModuleRun.module == ModuleName.SEARCH_CONSOLE,
            )
        )
    ).scalar_one_or_none()

    rows = await session.execute(
        sa.select(SearchConsoleMetric)
        .where(
            SearchConsoleMetric.scan_id == scan_id,
            SearchConsoleMetric.period == period,
            SearchConsoleMetric.dimension == dimension,
        )
        .order_by(SearchConsoleMetric.clicks.desc(), SearchConsoleMetric.impressions.desc())
        .limit(limit)
    )

    detail = module.detail if module is not None else None
    totals = dict(detail.get("totals", {})) if isinstance(detail, dict) else {}
    property_url = str(detail.get("property_url")) if isinstance(detail, dict) else None

    return ScanSearchConsoleResponse(
        scan_id=scan.id,
        module_status=module.status.value if module is not None else "no_ejecutado",
        module_detail=detail,
        property_url=property_url,
        totals=totals,
        metrics=[SearchConsoleMetricRead.model_validate(row) for row in rows.scalars()],
    )


@router.get(
    "/{scan_id}/scores",
    response_model=ScanScoresResponse,
    summary="Puntuaciones de la auditoría",
    responses=NOT_FOUND,
)
async def scan_scores(scan_id: uuid.UUID, findings: FindingServiceDep) -> ScanScoresResponse:
    """Devuelve el Softree Score y el Google Score por separado (§27)."""
    return await findings.scan_scores(scan_id)


@router.get(
    "/{scan_id}/comparison",
    response_model=ComparisonResponse,
    summary="Comparar con la auditoría anterior",
    responses={
        **NOT_FOUND,
        409: {
            "model": ErrorResponse,
            "description": "No hay auditoría anterior con la que comparar",
        },
    },
)
async def scan_comparison(
    scan_id: uuid.UUID,
    comparison: ComparisonServiceDep,
    against: Annotated[
        str, Query(description="`previous` o el identificador de otra auditoría del mismo sitio.")
    ] = "previous",
) -> ComparisonResponse:
    return ComparisonResponse.model_validate(await comparison.compare(scan_id, against))
