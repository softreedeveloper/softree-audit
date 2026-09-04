"""Endpoints de proyectos."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from softree_audit.api.deps import CurrentUser, DbSession
from softree_audit.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from softree_audit.projects.service import ProjectService
from softree_audit.schemas.common import ErrorResponse, Page
from softree_audit.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])

NOT_FOUND: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "El proyecto no existe"}
}


def get_service(session: DbSession, user: CurrentUser) -> ProjectService:
    return ProjectService(session, user.id)


ServiceDep = Annotated[ProjectService, Depends(get_service)]


@router.get("", response_model=Page[ProjectRead], summary="Listar proyectos")
async def list_projects(
    service: ServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> Page[ProjectRead]:
    items, next_cursor, total = await service.list(limit=limit, cursor=cursor)
    return Page[ProjectRead](items=items, next_cursor=next_cursor, total=total)


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un proyecto",
    responses={409: {"model": ErrorResponse, "description": "Nombre ya utilizado"}},
)
async def create_project(payload: ProjectCreate, service: ServiceDep) -> ProjectRead:
    return await service.create(payload)


@router.get(
    "/{project_id}", response_model=ProjectRead, summary="Obtener un proyecto", responses=NOT_FOUND
)
async def get_project(project_id: uuid.UUID, service: ServiceDep) -> ProjectRead:
    return await service.read(project_id)


@router.put(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Actualizar un proyecto",
    responses=NOT_FOUND,
)
async def update_project(
    project_id: uuid.UUID, payload: ProjectUpdate, service: ServiceDep
) -> ProjectRead:
    return await service.update(project_id, payload)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un proyecto",
    responses={
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "El proyecto todavía tiene sitios"},
    },
)
async def delete_project(
    project_id: uuid.UUID,
    service: ServiceDep,
    force: Annotated[
        bool,
        Query(description="Elimina también los sitios del proyecto y su histórico."),
    ] = False,
) -> None:
    await service.delete(project_id, force=force)
