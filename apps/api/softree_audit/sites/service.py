"""Servicio de sitios y de su scope.

Un sitio pertenece a un proyecto, y el proyecto a un usuario: toda consulta
recorre esa cadena para impedir el acceso a recursos ajenos (IDOR).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from softree_audit.core.errors import AppError, ConflictError, NotFoundError
from softree_audit.core.logging import get_logger
from softree_audit.core.pagination import decode_cursor, encode_cursor
from softree_audit.models import Project, Scan, Scope, Site
from softree_audit.schemas.scope import ScopeRead, ScopeUpdate
from softree_audit.schemas.site import SiteCreate, SiteDetail, SiteRead, SiteUpdate
from softree_audit.services.common.urls import hostname_of, matches_domain

logger = get_logger(__name__)


class ScopeExcludesSiteError(AppError):
    """El scope dejaría fuera la propia URL base del sitio."""

    status_code = 422
    code = "scope_excludes_site"
    message = "El scope debe incluir el dominio de la URL base del sitio."


class SiteService:
    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self._session = session
        self._owner_id = owner_id

    # ── Consultas ──────────────────────────────────────────────────────────

    def _owned(self) -> sa.ColumnElement[bool]:
        return Project.owner_id == self._owner_id

    async def list(
        self,
        *,
        project_id: uuid.UUID | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[SiteRead], str | None, int]:
        scans_count = (
            sa.select(sa.func.count())
            .select_from(Scan)
            .where(Scan.site_id == Site.id)
            .correlate(Site)
            .scalar_subquery()
        )

        base = (
            sa.select(Site, scans_count.label("scans_count"))
            .join(Project, Project.id == Site.project_id)
            .where(self._owned())
        )
        counter = (
            sa.select(sa.func.count())
            .select_from(Site)
            .join(Project, Project.id == Site.project_id)
            .where(self._owned())
        )

        if project_id is not None:
            base = base.where(Site.project_id == project_id)
            counter = counter.where(Site.project_id == project_id)

        statement = base.order_by(Site.id.desc()).limit(limit + 1)
        if cursor:
            statement = statement.where(Site.id < decode_cursor(cursor))

        rows = (await self._session.execute(statement)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]

        items = [
            SiteRead.model_validate(site).model_copy(update={"scans_count": count})
            for site, count in rows
        ]
        next_cursor = encode_cursor(items[-1].id) if has_more and items else None
        total = await self._session.scalar(counter)
        return items, next_cursor, int(total or 0)

    async def get(self, site_id: uuid.UUID) -> Site:
        result = await self._session.execute(
            sa.select(Site)
            .join(Project, Project.id == Site.project_id)
            .where(Site.id == site_id, self._owned())
            .options(selectinload(Site.scope))
        )
        site = result.scalar_one_or_none()
        if site is None:
            raise NotFoundError("El sitio no existe.")
        return site

    async def read(self, site_id: uuid.UUID) -> SiteDetail:
        site = await self.get(site_id)
        return await self._to_detail(site)

    # ── Escritura ──────────────────────────────────────────────────────────

    async def create(self, payload: SiteCreate) -> SiteDetail:
        await self._assert_project_owned(payload.project_id)

        site = Site(
            project_id=payload.project_id,
            name=payload.name,
            base_url=payload.base_url,
            authorized_by=payload.authorized_by,
            authorization_date=payload.authorization_date,
            authorization_notes=payload.authorization_notes,
            is_active=payload.is_active,
        )
        self._session.add(site)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("Ya existe un sitio con esa URL en el proyecto.") from exc

        # El scope se crea con valores por defecto seguros, acotado al host del
        # sitio (`docs/spec/api.md` §Scope).
        site.scope = Scope(allowed_domains=[hostname_of(site.base_url)])
        await self._session.flush()

        logger.info(
            "site.created",
            site_id=str(site.id),
            project_id=str(site.project_id),
            authorized=site.is_authorized,
        )
        return await self._to_detail(site)

    async def update(self, site_id: uuid.UUID, payload: SiteUpdate) -> SiteDetail:
        site = await self.get(site_id)
        previous_host = hostname_of(site.base_url)

        site.name = payload.name
        site.base_url = payload.base_url
        site.authorized_by = payload.authorized_by
        site.authorization_date = payload.authorization_date
        site.authorization_notes = payload.authorization_notes
        site.is_active = payload.is_active

        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError("Ya existe un sitio con esa URL en el proyecto.") from exc

        # Si cambia el host, el scope heredado dejaría de cubrir el sitio.
        new_host = hostname_of(site.base_url)
        if site.scope is not None and new_host != previous_host:
            domains = [domain for domain in site.scope.allowed_domains if domain != previous_host]
            if not any(matches_domain(new_host, domain) for domain in domains):
                domains.insert(0, new_host)
            site.scope.allowed_domains = domains
            await self._session.flush()
            logger.info("site.scope_realigned", site_id=str(site.id), host=new_host)

        logger.info("site.updated", site_id=str(site.id), authorized=site.is_authorized)
        return await self._to_detail(site)

    async def delete(self, site_id: uuid.UUID, *, force: bool = False) -> None:
        site = await self.get(site_id)
        scans = await self._scans_count(site_id)
        if scans and not force:
            raise ConflictError(
                f"El sitio tiene {scans} auditoría(s). Repite la operación con "
                "force=true si quieres eliminar también su histórico.",
                code="site_has_scans",
                details={"scans_count": scans},
            )
        await self._session.delete(site)
        await self._session.flush()
        logger.info("site.deleted", site_id=str(site_id), forced=force, scans=scans)

    # ── Scope ──────────────────────────────────────────────────────────────

    async def read_scope(self, site_id: uuid.UUID) -> ScopeRead:
        site = await self.get(site_id)
        return ScopeRead.model_validate(await self._ensure_scope(site))

    async def update_scope(self, site_id: uuid.UUID, payload: ScopeUpdate) -> ScopeRead:
        site = await self.get(site_id)
        scope = await self._ensure_scope(site)

        host = hostname_of(site.base_url)
        if not any(matches_domain(host, domain) for domain in payload.allowed_domains):
            raise ScopeExcludesSiteError(
                f"El dominio «{host}» de la URL base debe estar entre los dominios permitidos."
            )

        overlap = sorted(set(payload.allowed_paths) & set(payload.excluded_paths))
        if overlap:
            raise ScopeExcludesSiteError(
                "Hay rutas presentes a la vez en allowed_paths y excluded_paths: "
                + ", ".join(overlap),
                code="scope_path_conflict",
                details={"paths": overlap},
            )

        scope.allowed_domains = payload.allowed_domains
        scope.allowed_paths = payload.allowed_paths
        scope.excluded_paths = payload.excluded_paths
        scope.max_pages = payload.max_pages
        scope.max_depth = payload.max_depth
        scope.timeout_seconds = payload.timeout_seconds
        scope.request_delay_ms = payload.request_delay_ms
        scope.concurrency = payload.concurrency
        scope.respect_robots = payload.respect_robots
        scope.zap_spider_enabled = payload.zap_spider_enabled
        scope.check_external_links = payload.check_external_links

        await self._session.flush()
        logger.info(
            "scope.updated",
            site_id=str(site_id),
            domains=len(scope.allowed_domains),
            max_pages=scope.max_pages,
        )
        return ScopeRead.model_validate(scope)

    # ── Internos ───────────────────────────────────────────────────────────

    async def _assert_project_owned(self, project_id: uuid.UUID) -> None:
        exists = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(Project)
            .where(Project.id == project_id, Project.owner_id == self._owner_id)
        )
        if not exists:
            raise NotFoundError("El proyecto no existe.")

    async def _ensure_scope(self, site: Site) -> Scope:
        """Devuelve el scope del sitio, creándolo si faltara.

        Un sitio siempre debe tener scope; esto cubre registros creados antes de
        que existiera la creación automática.
        """
        if site.scope is None:
            site.scope = Scope(allowed_domains=[hostname_of(site.base_url)])
            await self._session.flush()
        return site.scope

    async def _scans_count(self, site_id: uuid.UUID) -> int:
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Scan).where(Scan.site_id == site_id)
        )
        return int(total or 0)

    async def _to_detail(self, site: Site) -> SiteDetail:
        await self._ensure_scope(site)
        return SiteDetail.model_validate(site).model_copy(
            update={"scans_count": await self._scans_count(site.id)}
        )
