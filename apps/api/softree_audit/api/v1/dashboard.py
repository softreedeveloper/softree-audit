"""Endpoint del dashboard (§28)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from softree_audit.api.deps import CurrentUser, DbSession
from softree_audit.comparison.service import ComparisonService
from softree_audit.schemas.comparison import DashboardResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_service(session: DbSession, user: CurrentUser) -> ComparisonService:
    return ComparisonService(session, user.id)


@router.get("", response_model=DashboardResponse, summary="Resumen de la plataforma")
async def dashboard(
    service: Annotated[ComparisonService, Depends(get_service)],
) -> DashboardResponse:
    """Agrega el estado **actual** de cada sitio, no la suma de su histórico."""
    return DashboardResponse.model_validate(await service.dashboard())
