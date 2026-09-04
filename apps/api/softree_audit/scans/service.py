"""Servicio de auditorías: validación previa, alta, consulta y cancelación.

`POST /scans` valida de forma sincrónica y rechaza rápido; el trabajo real se
encola. El cliente HTTP nunca espera bloqueado (RNF-01).
"""

from __future__ import annotations

import builtins
import datetime as dt
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from softree_audit.core.config import Settings
from softree_audit.core.errors import AppError, ConflictError, NotFoundError
from softree_audit.core.logging import get_logger
from softree_audit.core.pagination import decode_cursor, encode_cursor
from softree_audit.core.redis import RedisClient
from softree_audit.models import (
    ModuleStatus,
    Page,
    Project,
    Scan,
    ScanModuleRun,
    ScanStatus,
    ScanType,
    Scope,
    Site,
)
from softree_audit.scans import cancellation
from softree_audit.scans.modules import build_guard
from softree_audit.schemas.scan import PageRead, ScanDetail, ScanModuleRead, ScanRead
from softree_audit.services.common.url_guard import BlockedTargetError, ScopePolicy
from softree_audit.version import APP_VERSION, SCAN_ENGINE_VERSION

logger = get_logger(__name__)


class SiteNotAuthorizedError(AppError):
    status_code = 409
    code = "site_not_authorized"
    message = (
        "El sitio no tiene autorización registrada. Añada quién autoriza la auditoría y su fecha."
    )


class SiteInactiveError(AppError):
    status_code = 409
    code = "site_inactive"
    message = "El sitio está marcado como inactivo."


class TargetUnreachableError(AppError):
    status_code = 422
    code = "target_unreachable"
    message = "El objetivo no puede auditarse."


class ScanAlreadyFinishedError(AppError):
    status_code = 409
    code = "scan_already_finished"
    message = "La auditoría ya terminó y no puede cancelarse."


class ScanService:
    def __init__(
        self,
        session: AsyncSession,
        redis: RedisClient,
        settings: Settings,
        owner_id: uuid.UUID,
    ) -> None:
        self._session = session
        self._redis = redis
        self._settings = settings
        self._owner_id = owner_id

    # ── Alta ───────────────────────────────────────────────────────────────

    async def create(self, site_id: uuid.UUID, scan_type: ScanType) -> ScanDetail:
        site = await self._owned_site(site_id)

        if not site.is_active:
            raise SiteInactiveError()
        if not site.is_authorized:
            # Control de `docs/spec/security.md` §1: sin autorización no se audita.
            logger.warning("scan.rejected_unauthorized_site", site_id=str(site_id))
            raise SiteNotAuthorizedError()

        scope = site.scope
        if scope is None:
            raise ConflictError("El sitio no tiene scope configurado.")

        snapshot = self._snapshot(site, scope)
        policy = ScopePolicy.from_snapshot(snapshot)
        if not policy.permits(site.base_url):
            raise TargetUnreachableError(
                "El scope configurado no cubre la URL base del sitio.",
                code="scope_excludes_site",
            )

        # Validación de red antes de encolar: rechaza de inmediato un objetivo
        # que apunta a loopback, red privada o metadatos.
        guard = build_guard(self._settings)
        try:
            target = await guard.validate(site.base_url, scope=policy)
        except BlockedTargetError as exc:
            logger.warning(
                "scan.rejected_by_guard",
                site_id=str(site_id),
                reason=exc.reason,
                url=exc.url,
            )
            raise TargetUnreachableError(
                f"El objetivo no puede auditarse: {exc}", details={"reason": exc.reason}
            ) from exc

        scan = Scan(
            site_id=site.id,
            triggered_by=self._owner_id,
            scan_type=scan_type,
            status=ScanStatus.QUEUED,
            progress=0,
            scope_snapshot=snapshot,
            engine_version=SCAN_ENGINE_VERSION,
            app_version=APP_VERSION,
        )
        self._session.add(scan)
        await self._session.flush()

        logger.info(
            "scan.created",
            scan_id=str(scan.id),
            site_id=str(site.id),
            scan_type=scan_type.value,
            resolved_ip=str(target.ip),
        )
        return await self._detail(scan, site)

    @staticmethod
    def _snapshot(site: Site, scope: Scope) -> dict[str, Any]:
        """Scope efectivo del scan, congelado para hacerlo reproducible."""
        return {
            "base_url": site.base_url,
            "site_name": site.name,
            "allowed_domains": list(scope.allowed_domains),
            "allowed_paths": list(scope.allowed_paths),
            "excluded_paths": list(scope.excluded_paths),
            "max_pages": scope.max_pages,
            "max_depth": scope.max_depth,
            "timeout_seconds": scope.timeout_seconds,
            "request_delay_ms": scope.request_delay_ms,
            "concurrency": scope.concurrency,
            "respect_robots": scope.respect_robots,
            "zap_spider_enabled": scope.zap_spider_enabled,
            "check_external_links": scope.check_external_links,
        }

    # ── Consulta ───────────────────────────────────────────────────────────

    async def list(
        self,
        *,
        site_id: uuid.UUID | None,
        status: ScanStatus | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[builtins.list[ScanRead], str | None, int]:
        pages_count = (
            sa.select(sa.func.count())
            .select_from(Page)
            .where(Page.scan_id == Scan.id)
            .correlate(Scan)
            .scalar_subquery()
        )
        base = (
            sa.select(Scan, Site.name, Site.base_url, pages_count.label("pages_count"))
            .join(Site, Site.id == Scan.site_id)
            .join(Project, Project.id == Site.project_id)
            .where(Project.owner_id == self._owner_id)
        )
        counter = (
            sa.select(sa.func.count())
            .select_from(Scan)
            .join(Site, Site.id == Scan.site_id)
            .join(Project, Project.id == Site.project_id)
            .where(Project.owner_id == self._owner_id)
        )
        if site_id is not None:
            base = base.where(Scan.site_id == site_id)
            counter = counter.where(Scan.site_id == site_id)
        if status is not None:
            base = base.where(Scan.status == status)
            counter = counter.where(Scan.status == status)

        statement = base.order_by(Scan.id.desc()).limit(limit + 1)
        if cursor:
            statement = statement.where(Scan.id < decode_cursor(cursor))

        rows = (await self._session.execute(statement)).all()
        has_more = len(rows) > limit
        rows = rows[:limit]

        items = [
            ScanRead.model_validate(scan).model_copy(
                update={
                    "site_name": name,
                    "site_base_url": base_url,
                    "pages_count": count,
                }
            )
            for scan, name, base_url, count in rows
        ]
        next_cursor = encode_cursor(items[-1].id) if has_more and items else None
        total = await self._session.scalar(counter)
        return items, next_cursor, int(total or 0)

    async def get(self, scan_id: uuid.UUID) -> Scan:
        result = await self._session.execute(
            sa.select(Scan)
            .join(Site, Site.id == Scan.site_id)
            .join(Project, Project.id == Site.project_id)
            .where(Scan.id == scan_id, Project.owner_id == self._owner_id)
            .options(selectinload(Scan.modules), selectinload(Scan.site))
        )
        scan = result.scalar_one_or_none()
        if scan is None:
            raise NotFoundError("La auditoría no existe.")
        return scan

    async def read(self, scan_id: uuid.UUID) -> ScanDetail:
        scan = await self.get(scan_id)
        return await self._detail(scan, scan.site)

    async def modules(self, scan_id: uuid.UUID) -> builtins.list[ScanModuleRead]:
        scan = await self.get(scan_id)
        return [ScanModuleRead.model_validate(module) for module in scan.modules]

    async def pages(
        self, scan_id: uuid.UUID, *, limit: int, cursor: str | None
    ) -> tuple[builtins.list[PageRead], str | None, int]:
        await self.get(scan_id)

        statement = (
            sa.select(Page).where(Page.scan_id == scan_id).order_by(Page.id.asc()).limit(limit + 1)
        )
        if cursor:
            statement = statement.where(Page.id > decode_cursor(cursor))

        rows = list((await self._session.execute(statement)).scalars())
        has_more = len(rows) > limit
        rows = rows[:limit]

        items = [PageRead.model_validate(page) for page in rows]
        next_cursor = encode_cursor(items[-1].id) if has_more and items else None
        total = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Page).where(Page.scan_id == scan_id)
        )
        return items, next_cursor, int(total or 0)

    # ── Cancelación ────────────────────────────────────────────────────────

    async def cancel(self, scan_id: uuid.UUID) -> ScanDetail:
        scan = await self.get(scan_id)
        if scan.status.is_terminal:
            raise ScanAlreadyFinishedError()

        await cancellation.request_cancel(self._redis, scan_id)

        if scan.status is ScanStatus.QUEUED:
            # Todavía no la tomó el worker: se cierra aquí mismo.
            scan.status = ScanStatus.CANCELLED
            # Valor calculado en Python: una expresión SQL dejaría el atributo
            # expirado y forzaría una recarga perezosa al serializar.
            scan.finished_at = dt.datetime.now(dt.UTC)
            await self._session.execute(
                sa.update(ScanModuleRun)
                .where(
                    ScanModuleRun.scan_id == scan_id,
                    ScanModuleRun.status == ModuleStatus.PENDING,
                )
                .values(status=ModuleStatus.SKIPPED, detail={"reason": "cancelled"})
            )
            await self._session.flush()

        logger.info("scan.cancel_requested", scan_id=str(scan_id), status=scan.status.value)
        return await self._detail(scan, scan.site)

    # ── Internos ───────────────────────────────────────────────────────────

    async def _owned_site(self, site_id: uuid.UUID) -> Site:
        result = await self._session.execute(
            sa.select(Site)
            .join(Project, Project.id == Site.project_id)
            .where(Site.id == site_id, Project.owner_id == self._owner_id)
            .options(selectinload(Site.scope))
        )
        site = result.scalar_one_or_none()
        if site is None:
            raise NotFoundError("El sitio no existe.")
        return site

    async def _detail(self, scan: Scan, site: Site) -> ScanDetail:
        pages = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Page).where(Page.scan_id == scan.id)
        )
        modules = await self._session.execute(
            sa.select(ScanModuleRun)
            .where(ScanModuleRun.scan_id == scan.id)
            .order_by(ScanModuleRun.created_at.asc())
        )
        # `ScanDetail` se construye a partir de `ScanRead`, no directamente del
        # ORM: validar el modelo completo tocaría la relación `modules`, que es
        # perezosa y provocaría IO fuera del contexto asíncrono.
        base = ScanRead.model_validate(scan)
        return ScanDetail(
            **base.model_dump(exclude={"site_name", "site_base_url", "pages_count"}),
            site_name=site.name,
            site_base_url=site.base_url,
            pages_count=int(pages or 0),
            scope_snapshot=dict(scan.scope_snapshot),
            modules=[ScanModuleRead.model_validate(module) for module in modules.scalars()],
        )
