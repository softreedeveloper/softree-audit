"""Servicio de proyectos.

Toda consulta filtra por la pertenencia del recurso. Un identificador válido de
otro usuario devuelve 404, no 403, para no confirmar su existencia
(`docs/spec/security.md` §6).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from softree_audit.core.errors import ConflictError, NotFoundError
from softree_audit.core.logging import get_logger
from softree_audit.core.pagination import decode_cursor, encode_cursor
from softree_audit.models import Project, Site
from softree_audit.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

logger = get_logger(__name__)


class ProjectService:
    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self._session = session
        self._owner_id = owner_id

    async def list(
        self, *, limit: int, cursor: str | None
    ) -> tuple[list[ProjectRead], str | None, int]:
        sites_count = (
            sa.select(sa.func.count())
            .select_from(Site)
            .where(Site.project_id == Project.id)
            .correlate(Project)
            .scalar_subquery()
        )

        statement = (
            sa.select(Project, sites_count.label("sites_count"))
            .where(Project.owner_id == self._owner_id)
            .order_by(Project.id.desc())
            .limit(limit + 1)
        )
        if cursor:
            statement = statement.where(Project.id < decode_cursor(cursor))

        rows = (await self._session.execute(statement)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]

        items = [
            ProjectRead.model_validate(project).model_copy(update={"sites_count": count})
            for project, count in rows
        ]
        next_cursor = encode_cursor(items[-1].id) if has_more and items else None

        total = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(Project)
            .where(Project.owner_id == self._owner_id)
        )
        return items, next_cursor, int(total or 0)

    async def get(self, project_id: uuid.UUID) -> Project:
        result = await self._session.execute(
            sa.select(Project).where(Project.id == project_id, Project.owner_id == self._owner_id)
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise NotFoundError("El proyecto no existe.")
        return project

    async def read(self, project_id: uuid.UUID) -> ProjectRead:
        project = await self.get(project_id)
        return ProjectRead.model_validate(project).model_copy(
            update={"sites_count": await self._sites_count(project_id)}
        )

    async def create(self, payload: ProjectCreate) -> ProjectRead:
        project = Project(
            owner_id=self._owner_id,
            name=payload.name,
            client_name=payload.client_name,
            notes=payload.notes,
        )
        self._session.add(project)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("Ya existe un proyecto con ese nombre.") from exc

        logger.info("project.created", project_id=str(project.id), owner_id=str(self._owner_id))
        return ProjectRead.model_validate(project).model_copy(update={"sites_count": 0})

    async def update(self, project_id: uuid.UUID, payload: ProjectUpdate) -> ProjectRead:
        project = await self.get(project_id)
        project.name = payload.name
        project.client_name = payload.client_name
        project.notes = payload.notes
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("Ya existe un proyecto con ese nombre.") from exc

        logger.info("project.updated", project_id=str(project.id))
        return ProjectRead.model_validate(project).model_copy(
            update={"sites_count": await self._sites_count(project_id)}
        )

    async def delete(self, project_id: uuid.UUID, *, force: bool = False) -> None:
        project = await self.get(project_id)
        sites = await self._sites_count(project_id)
        if sites and not force:
            raise ConflictError(
                f"El proyecto tiene {sites} sitio(s). Bórralos primero o repite la "
                "operación con force=true, que eliminará también sus auditorías.",
                code="project_has_sites",
                details={"sites_count": sites},
            )
        await self._session.delete(project)
        await self._session.flush()
        logger.info("project.deleted", project_id=str(project_id), forced=force, sites=sites)

    async def _sites_count(self, project_id: uuid.UUID) -> int:
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Site).where(Site.project_id == project_id)
        )
        return int(total or 0)
