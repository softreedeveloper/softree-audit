"""Endpoints de hallazgos."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from softree_audit.api.deps import CurrentUser, DbSession
from softree_audit.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from softree_audit.findings.service import FindingService
from softree_audit.models.enums import (
    FindingCategory,
    FindingSource,
    FindingStatus,
    Severity,
)
from softree_audit.schemas.common import ErrorResponse, Page
from softree_audit.schemas.finding import FindingRead, FindingStatusUpdate

router = APIRouter(prefix="/findings", tags=["findings"])

NOT_FOUND: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "El hallazgo no existe"}
}


def get_service(session: DbSession, user: CurrentUser) -> FindingService:
    return FindingService(session, user.id)


ServiceDep = Annotated[FindingService, Depends(get_service)]


@router.get("", response_model=Page[FindingRead], summary="Listar hallazgos")
async def list_findings(
    service: ServiceDep,
    scan_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    severity: Severity | None = None,
    source: FindingSource | None = None,
    category: FindingCategory | None = None,
    status: FindingStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page[FindingRead]:
    items, next_cursor, total = await service.list(
        scan_id=scan_id,
        site_id=site_id,
        severity=severity,
        source=source,
        category=category,
        status=status,
        limit=limit,
        cursor=cursor,
    )
    return Page[FindingRead](items=items, next_cursor=next_cursor, total=total)


@router.patch(
    "/{finding_id}",
    response_model=FindingRead,
    summary="Cambiar el estado de un hallazgo",
    responses=NOT_FOUND,
)
async def update_finding(
    finding_id: uuid.UUID, payload: FindingStatusUpdate, service: ServiceDep
) -> FindingRead:
    """Permite marcar un hallazgo como corregido, aceptado o falso positivo."""
    return await service.set_status(finding_id, payload.status)
