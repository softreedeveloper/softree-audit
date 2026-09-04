"""Endpoints de sitios y de su scope."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from softree_audit.api.deps import CurrentUser, DbSession
from softree_audit.comparison.service import ComparisonService
from softree_audit.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from softree_audit.findings.service import FindingService
from softree_audit.schemas.common import ErrorResponse, Page
from softree_audit.schemas.comparison import HistoryEntry
from softree_audit.schemas.finding import (
    SitePerformanceSummary,
    SiteSecuritySummary,
    SiteSeoSummary,
)
from softree_audit.schemas.scope import ScopeLimits, ScopeRead, ScopeUpdate
from softree_audit.schemas.site import SiteCreate, SiteDetail, SiteRead, SiteUpdate
from softree_audit.sites.service import SiteService

router = APIRouter(prefix="/sites", tags=["sites"])

NOT_FOUND: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "El sitio no existe"}
}


def get_service(session: DbSession, user: CurrentUser) -> SiteService:
    return SiteService(session, user.id)


def get_finding_service(session: DbSession, user: CurrentUser) -> FindingService:
    return FindingService(session, user.id)


ServiceDep = Annotated[SiteService, Depends(get_service)]


def get_comparison_service(session: DbSession, user: CurrentUser) -> ComparisonService:
    return ComparisonService(session, user.id)


FindingServiceDep = Annotated[FindingService, Depends(get_finding_service)]
ComparisonServiceDep = Annotated[ComparisonService, Depends(get_comparison_service)]


@router.get("", response_model=Page[SiteRead], summary="Listar sitios")
async def list_sites(
    service: ServiceDep,
    project_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page[SiteRead]:
    items, next_cursor, total = await service.list(
        project_id=project_id, limit=limit, cursor=cursor
    )
    return Page[SiteRead](items=items, next_cursor=next_cursor, total=total)


@router.get(
    "/scope-limits",
    response_model=ScopeLimits,
    summary="Máximos admitidos para el scope",
)
async def scope_limits(_user: CurrentUser) -> ScopeLimits:
    """Los máximos viven en el servidor; la interfaz los consulta en vez de duplicarlos."""
    return ScopeLimits()


@router.post(
    "",
    response_model=SiteDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un sitio",
    responses={
        404: {"model": ErrorResponse, "description": "El proyecto no existe"},
        409: {"model": ErrorResponse, "description": "URL ya registrada en el proyecto"},
    },
)
async def create_site(payload: SiteCreate, service: ServiceDep) -> SiteDetail:
    return await service.create(payload)


@router.get(
    "/{site_id}", response_model=SiteDetail, summary="Obtener un sitio", responses=NOT_FOUND
)
async def get_site(site_id: uuid.UUID, service: ServiceDep) -> SiteDetail:
    return await service.read(site_id)


@router.put(
    "/{site_id}", response_model=SiteDetail, summary="Actualizar un sitio", responses=NOT_FOUND
)
async def update_site(site_id: uuid.UUID, payload: SiteUpdate, service: ServiceDep) -> SiteDetail:
    return await service.update(site_id, payload)


@router.delete(
    "/{site_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un sitio",
    responses={
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "El sitio tiene auditorías"},
    },
)
async def delete_site(
    site_id: uuid.UUID,
    service: ServiceDep,
    force: Annotated[
        bool, Query(description="Elimina también el histórico de auditorías del sitio.")
    ] = False,
) -> None:
    await service.delete(site_id, force=force)


@router.get(
    "/{site_id}/scope", response_model=ScopeRead, summary="Obtener el scope", responses=NOT_FOUND
)
async def get_scope(site_id: uuid.UUID, service: ServiceDep) -> ScopeRead:
    return await service.read_scope(site_id)


@router.put(
    "/{site_id}/scope",
    response_model=ScopeRead,
    summary="Actualizar el scope",
    responses={
        **NOT_FOUND,
        422: {"model": ErrorResponse, "description": "El scope no cubre la URL base del sitio"},
    },
)
async def update_scope(site_id: uuid.UUID, payload: ScopeUpdate, service: ServiceDep) -> ScopeRead:
    return await service.update_scope(site_id, payload)


@router.get(
    "/{site_id}/seo",
    response_model=SiteSeoSummary,
    summary="Último resultado SEO del sitio",
    responses={
        404: {
            "model": ErrorResponse,
            "description": "El sitio no existe o todavía no tiene auditorías terminadas",
        }
    },
)
async def site_seo(site_id: uuid.UUID, findings: FindingServiceDep) -> SiteSeoSummary:
    return await findings.site_seo_summary(site_id)


@router.get(
    "/{site_id}/security",
    response_model=SiteSecuritySummary,
    summary="Último resultado de seguridad del sitio",
    responses={
        404: {
            "model": ErrorResponse,
            "description": "El sitio no existe o todavía no tiene auditorías terminadas",
        }
    },
)
async def site_security(site_id: uuid.UUID, findings: FindingServiceDep) -> SiteSecuritySummary:
    return await findings.site_security_summary(site_id)


@router.get(
    "/{site_id}/performance",
    response_model=SitePerformanceSummary,
    summary="Último resultado de rendimiento del sitio",
    responses={
        404: {
            "model": ErrorResponse,
            "description": "El sitio no existe o todavía no tiene auditorías terminadas",
        }
    },
)
async def site_performance(
    site_id: uuid.UUID, findings: FindingServiceDep
) -> SitePerformanceSummary:
    return await findings.site_performance_summary(site_id)


@router.get(
    "/{site_id}/history",
    response_model=list[HistoryEntry],
    summary="Histórico de auditorías del sitio",
    responses=NOT_FOUND,
)
async def site_history(
    site_id: uuid.UUID,
    comparison: ComparisonServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50,
) -> list[HistoryEntry]:
    return [
        HistoryEntry.model_validate(entry)
        for entry in await comparison.history(site_id, limit=limit)
    ]
