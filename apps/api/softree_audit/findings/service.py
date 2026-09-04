"""Servicio de findings.

El motor completo (agregación entre fuentes, arrastre de estado entre scans y
scoring) llega en el Slice 8. Aquí viven la consulta y el cambio de estado que
el motor SEO ya necesita.
"""

from __future__ import annotations

import builtins
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from softree_audit.core.errors import NotFoundError
from softree_audit.core.logging import get_logger
from softree_audit.core.pagination import decode_cursor, encode_cursor
from softree_audit.models import (
    Finding,
    FindingCategory,
    FindingSource,
    FindingStatus,
    ModuleName,
    PerformanceResult,
    Project,
    Scan,
    ScanModuleRun,
    ScanStatus,
    Score,
    ScoreCategory,
    ScoreSystem,
    SEOResult,
    Severity,
    Site,
)
from softree_audit.schemas.finding import (
    FindingRead,
    GoogleScoreRead,
    PerformanceResultRead,
    ScanScoresResponse,
    ScoreRead,
    SeoResultRead,
    SeverityCounts,
    SitePerformanceSummary,
    SiteSecuritySummary,
    SiteSeoSummary,
)

logger = get_logger(__name__)

# Orden de presentación: primero lo más grave.
SEVERITY_ORDER = sa.case(
    {
        Severity.CRITICAL.value: 0,
        Severity.HIGH.value: 1,
        Severity.MEDIUM.value: 2,
        Severity.LOW.value: 3,
        Severity.INFO.value: 4,
    },
    value=Finding.severity,
    else_=5,
)


class FindingService:
    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self._session = session
        self._owner_id = owner_id

    def _owned(self) -> sa.ColumnElement[bool]:
        return Project.owner_id == self._owner_id

    def _base_query(self) -> sa.Select[tuple[Finding]]:
        return (
            sa.select(Finding)
            .join(Scan, Scan.id == Finding.scan_id)
            .join(Site, Site.id == Scan.site_id)
            .join(Project, Project.id == Site.project_id)
            .where(self._owned())
        )

    async def list(
        self,
        *,
        scan_id: uuid.UUID | None = None,
        site_id: uuid.UUID | None = None,
        severity: Severity | None = None,
        source: FindingSource | None = None,
        category: FindingCategory | None = None,
        status: FindingStatus | None = None,
        limit: int,
        cursor: str | None,
    ) -> tuple[builtins.list[FindingRead], str | None, int]:
        filters: list[sa.ColumnElement[bool]] = []
        if scan_id is not None:
            filters.append(Finding.scan_id == scan_id)
        if site_id is not None:
            filters.append(Scan.site_id == site_id)
        if severity is not None:
            filters.append(Finding.severity == severity)
        if source is not None:
            filters.append(Finding.source == source)
        if category is not None:
            filters.append(Finding.category == category)
        if status is not None:
            filters.append(Finding.status == status)

        statement = self._base_query().where(*filters)
        counter = (
            sa.select(sa.func.count())
            .select_from(Finding)
            .join(Scan, Scan.id == Finding.scan_id)
            .join(Site, Site.id == Scan.site_id)
            .join(Project, Project.id == Site.project_id)
            .where(self._owned(), *filters)
        )

        statement = statement.order_by(SEVERITY_ORDER.asc(), Finding.id.asc()).limit(limit + 1)
        if cursor:
            statement = statement.where(Finding.id > decode_cursor(cursor))

        rows = list((await self._session.execute(statement)).scalars())
        has_more = len(rows) > limit
        rows = rows[:limit]

        items = [FindingRead.model_validate(row) for row in rows]
        next_cursor = encode_cursor(items[-1].id) if has_more and items else None
        total = await self._session.scalar(counter)
        return items, next_cursor, int(total or 0)

    async def get(self, finding_id: uuid.UUID) -> Finding:
        result = await self._session.execute(self._base_query().where(Finding.id == finding_id))
        finding = result.scalar_one_or_none()
        if finding is None:
            raise NotFoundError("El hallazgo no existe.")
        return finding

    async def set_status(self, finding_id: uuid.UUID, status: FindingStatus) -> FindingRead:
        finding = await self.get(finding_id)
        previous = finding.status
        finding.status = status
        await self._session.flush()
        logger.info(
            "finding.status_changed",
            finding_id=str(finding_id),
            rule_id=finding.rule_id,
            previous=previous.value,
            status=status.value,
        )
        return FindingRead.model_validate(finding)

    async def severity_counts(
        self, *, scan_id: uuid.UUID | None = None, site_id: uuid.UUID | None = None
    ) -> SeverityCounts:
        filters: list[sa.ColumnElement[bool]] = []
        if scan_id is not None:
            filters.append(Finding.scan_id == scan_id)
        if site_id is not None:
            filters.append(Scan.site_id == site_id)

        rows = await self._session.execute(
            sa.select(Finding.severity, sa.func.count())
            .join(Scan, Scan.id == Finding.scan_id)
            .join(Site, Site.id == Scan.site_id)
            .join(Project, Project.id == Site.project_id)
            .where(self._owned(), Finding.status == FindingStatus.OPEN, *filters)
            .group_by(Finding.severity)
        )
        counts = SeverityCounts()
        for severity, total in rows:
            setattr(counts, severity.value, int(total))
        return counts

    async def site_seo_summary(self, site_id: uuid.UUID) -> SiteSeoSummary:
        """Último scan terminado del sitio con resultado SEO."""
        scan = await self._last_finished_scan(site_id)

        result = (
            await self._session.execute(sa.select(SEOResult).where(SEOResult.scan_id == scan.id))
        ).scalar_one_or_none()

        rules = await self._session.execute(
            sa.select(Finding.rule_id, Finding.title, Finding.severity, sa.func.count())
            .where(
                Finding.scan_id == scan.id,
                Finding.source == FindingSource.SEO,
                Finding.status == FindingStatus.OPEN,
            )
            .group_by(Finding.rule_id, Finding.title, Finding.severity)
            .order_by(sa.func.count().desc())
            .limit(10)
        )

        return SiteSeoSummary(
            scan_id=scan.id,
            scan_status=scan.status.value,
            finished_at=scan.finished_at,
            result=SeoResultRead.model_validate(result) if result is not None else None,
            findings_by_severity=await self.severity_counts(scan_id=scan.id),
            top_rules=[
                {
                    "rule_id": rule_id,
                    "title": title,
                    "severity": severity.value,
                    "count": int(count),
                }
                for rule_id, title, severity, count in rules
            ],
        )

    async def _last_finished_scan(self, site_id: uuid.UUID) -> Scan:
        owned_site = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(Site)
            .join(Project, Project.id == Site.project_id)
            .where(Site.id == site_id, self._owned())
        )
        if not owned_site:
            raise NotFoundError("El sitio no existe.")

        scan = (
            await self._session.execute(
                sa.select(Scan)
                .where(
                    Scan.site_id == site_id,
                    Scan.status.in_([ScanStatus.COMPLETED, ScanStatus.PARTIAL]),
                )
                .order_by(Scan.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if scan is None:
            raise NotFoundError("El sitio todavía no tiene auditorías terminadas.")
        return scan

    async def site_security_summary(self, site_id: uuid.UUID) -> SiteSecuritySummary:
        """Resultado de seguridad del último scan terminado del sitio."""
        scan = await self._last_finished_scan(site_id)

        module = (
            await self._session.execute(
                sa.select(ScanModuleRun).where(
                    ScanModuleRun.scan_id == scan.id,
                    ScanModuleRun.module == ModuleName.SECURITY,
                )
            )
        ).scalar_one_or_none()

        top = await self._session.execute(
            sa.select(Finding)
            .where(
                Finding.scan_id == scan.id,
                Finding.source == FindingSource.ZAP,
                Finding.status == FindingStatus.OPEN,
            )
            .order_by(SEVERITY_ORDER.asc(), Finding.occurrences.desc())
            .limit(10)
        )

        return SiteSecuritySummary(
            scan_id=scan.id,
            scan_status=scan.status.value,
            finished_at=scan.finished_at,
            # Si el módulo no llegó a ejecutarse hay que decirlo, no dar por
            # supuesto que el sitio está limpio.
            module_status=module.status.value if module is not None else "no_ejecutado",
            module_detail=module.detail if module is not None else None,
            findings_by_severity=await self.severity_counts(scan_id=scan.id),
            top_findings=[
                {
                    "rule_id": finding.rule_id,
                    "title": finding.title,
                    "severity": finding.severity.value,
                    "confidence": finding.confidence.value,
                    "occurrences": finding.occurrences,
                    "cwe": finding.cwe,
                    "owasp": finding.owasp,
                }
                for finding in top.scalars()
            ],
        )

    async def site_performance_summary(self, site_id: uuid.UUID) -> SitePerformanceSummary:
        """Rendimiento del último scan terminado del sitio.

        Devuelve el Google Score sin transformar; el Softree Score es otra cosa
        y se calcula aparte (§27).
        """
        scan = await self._last_finished_scan(site_id)

        module = (
            await self._session.execute(
                sa.select(ScanModuleRun).where(
                    ScanModuleRun.scan_id == scan.id,
                    ScanModuleRun.module == ModuleName.PERFORMANCE,
                )
            )
        ).scalar_one_or_none()

        results = await self._session.execute(
            sa.select(PerformanceResult)
            .where(PerformanceResult.scan_id == scan.id)
            .order_by(PerformanceResult.strategy.asc())
        )
        scores = await self._session.execute(
            sa.select(Score).where(Score.scan_id == scan.id, Score.system == ScoreSystem.GOOGLE)
        )

        return SitePerformanceSummary(
            scan_id=scan.id,
            scan_status=scan.status.value,
            finished_at=scan.finished_at,
            module_status=module.status.value if module is not None else "no_ejecutado",
            module_detail=module.detail if module is not None else None,
            results=[
                PerformanceResultRead.model_validate(row).model_copy(
                    update={"strategy": row.strategy.value}
                )
                for row in results.scalars()
            ],
            google_scores=[
                GoogleScoreRead(
                    category=score.category.value, value=score.value, detail=score.detail
                )
                for score in scores.scalars()
            ],
            findings_by_severity=await self.severity_counts(scan_id=scan.id),
        )

    async def scan_scores(self, scan_id: uuid.UUID) -> ScanScoresResponse:
        """Puntuaciones del scan, separadas por sistema."""
        owned = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(Scan)
            .join(Site, Site.id == Scan.site_id)
            .join(Project, Project.id == Site.project_id)
            .where(Scan.id == scan_id, self._owned())
        )
        if not owned:
            raise NotFoundError("La auditoría no existe.")

        rows = list(
            (
                await self._session.execute(
                    sa.select(Score).where(Score.scan_id == scan_id).order_by(Score.category)
                )
            ).scalars()
        )

        softree = [row for row in rows if row.system is ScoreSystem.SOFTREE]
        google = [row for row in rows if row.system is ScoreSystem.GOOGLE]
        overall = next((row for row in softree if row.category is ScoreCategory.OVERALL), None)

        return ScanScoresResponse(
            scan_id=scan_id,
            softree=[_score_read(row) for row in softree],
            google=[_score_read(row) for row in google],
            softree_overall=overall.value if overall is not None else None,
            band=str(overall.detail.get("band")) if overall is not None else None,
            findings_by_severity=await self.severity_counts(scan_id=scan_id),
        )


def _score_read(row: Score) -> ScoreRead:
    return ScoreRead(
        system=row.system.value,
        category=row.category.value,
        value=row.value,
        weight=row.weight,
        detail=row.detail,
        engine_version=row.engine_version,
    )
