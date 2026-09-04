"""Lectura de los datos que la comparación necesita, y dashboard agregado."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from softree_audit.comparison.engine import FindingSnapshot, compare
from softree_audit.core.errors import ConflictError, NotFoundError
from softree_audit.models import (
    Finding,
    FindingSource,
    FindingStatus,
    ModuleName,
    ModuleStatus,
    PageSpeedStrategy,
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

TERMINAL_WITH_DATA = (ScanStatus.COMPLETED, ScanStatus.PARTIAL)


class NoPreviousScanError(ConflictError):
    code = "no_previous_scan"
    message = "No hay una auditoría anterior de este sitio con la que comparar."


class ComparisonService:
    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self._session = session
        self._owner_id = owner_id

    def _owned(self) -> sa.ColumnElement[bool]:
        return Project.owner_id == self._owner_id

    async def _owned_scan(self, scan_id: uuid.UUID) -> Scan:
        scan = (
            await self._session.execute(
                sa.select(Scan)
                .join(Site, Site.id == Scan.site_id)
                .join(Project, Project.id == Site.project_id)
                .where(Scan.id == scan_id, self._owned())
            )
        ).scalar_one_or_none()
        if scan is None:
            raise NotFoundError("La auditoría no existe.")
        return scan

    async def _previous_scan(self, scan: Scan) -> Scan:
        previous = (
            await self._session.execute(
                sa.select(Scan)
                .where(
                    Scan.site_id == scan.site_id,
                    Scan.id < scan.id,
                    Scan.status.in_(TERMINAL_WITH_DATA),
                )
                .order_by(Scan.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if previous is None:
            raise NoPreviousScanError()
        return previous

    async def compare(self, scan_id: uuid.UUID, against: str | None = None) -> dict[str, Any]:
        """Compara una auditoría con la anterior o con otra indicada."""
        current = await self._owned_scan(scan_id)

        if against and against != "previous":
            try:
                other_id = uuid.UUID(against)
            except ValueError as exc:
                raise NotFoundError("La auditoría de referencia no existe.") from exc
            previous = await self._owned_scan(other_id)
            if previous.site_id != current.site_id:
                # Comparar sitios distintos no significa nada.
                raise ConflictError(
                    "Solo pueden compararse auditorías del mismo sitio.",
                    code="different_site",
                )
        else:
            previous = await self._previous_scan(current)

        result = compare(
            previous_findings=await self._findings(previous.id),
            current_findings=await self._findings(current.id),
            previous_metrics=await self._metrics(previous.id),
            current_metrics=await self._metrics(current.id),
            previous_sources=await self._sources(previous.id),
            current_sources=await self._sources(current.id),
        )
        return {
            "current": self._scan_ref(current),
            "previous": self._scan_ref(previous),
            **result.as_dict(),
        }

    @staticmethod
    def _scan_ref(scan: Scan) -> dict[str, Any]:
        return {
            "scan_id": scan.id,
            "status": scan.status.value,
            "finished_at": scan.finished_at,
            "engine_version": scan.engine_version,
        }

    async def _sources(self, scan_id: uuid.UUID) -> set[str]:
        """Fuentes de hallazgos que esta auditoría llegó a medir.

        Un módulo omitido o fallido no midió nada, así que sus hallazgos no
        pueden compararse: incluirlos haría creer que se corrigieron.
        """
        rows = await self._session.execute(
            sa.select(ScanModuleRun.module).where(
                ScanModuleRun.scan_id == scan_id,
                ScanModuleRun.status == ModuleStatus.COMPLETED,
            )
        )
        by_module = {
            ModuleName.SEO: FindingSource.SEO,
            ModuleName.SECURITY: FindingSource.ZAP,
            ModuleName.PERFORMANCE: FindingSource.PAGESPEED,
            ModuleName.CRAWLER: FindingSource.CRAWLER,
            ModuleName.SEARCH_CONSOLE: FindingSource.SEARCH_CONSOLE,
        }
        return {by_module[module].value for (module,) in rows if module in by_module}

    async def _findings(self, scan_id: uuid.UUID) -> list[FindingSnapshot]:
        rows = await self._session.execute(sa.select(Finding).where(Finding.scan_id == scan_id))
        return [
            FindingSnapshot(
                fingerprint=row.fingerprint,
                rule_id=row.rule_id,
                title=row.title,
                severity=row.severity.value,
                category=row.category.value,
                occurrences=row.occurrences,
                source=row.source.value,
                url=row.url,
                is_open=row.status is FindingStatus.OPEN,
            )
            for row in rows.scalars()
        ]

    async def _metrics(self, scan_id: uuid.UUID) -> dict[str, float | None]:
        metrics: dict[str, float | None] = {}

        scores = await self._session.execute(
            sa.select(Score.category, Score.value).where(
                Score.scan_id == scan_id, Score.system == ScoreSystem.SOFTREE
            )
        )
        for category, value in scores:
            if value is None:
                continue
            key = (
                "softree_overall"
                if category is ScoreCategory.OVERALL
                else f"{category.value}_score"
            )
            metrics[key] = float(value)

        seo = (
            await self._session.execute(sa.select(SEOResult).where(SEOResult.scan_id == scan_id))
        ).scalar_one_or_none()
        if seo is not None:
            metrics.update(
                {
                    "pages_crawled": float(seo.pages_crawled),
                    "broken_internal_links": float(seo.broken_internal_links),
                    "missing_title": float(seo.missing_title),
                    "missing_description": float(seo.missing_description),
                    "missing_h1": float(seo.missing_h1),
                    "images_missing_alt": float(seo.images_missing_alt),
                }
            )

        performance = (
            await self._session.execute(
                sa.select(PerformanceResult).where(
                    PerformanceResult.scan_id == scan_id,
                    PerformanceResult.strategy == PageSpeedStrategy.MOBILE,
                )
            )
        ).scalar_one_or_none()
        if performance is not None:
            if performance.lcp_ms is not None:
                metrics["lcp_ms"] = float(performance.lcp_ms)
            if performance.cls is not None:
                metrics["cls"] = float(performance.cls)
            if performance.tbt_ms is not None:
                metrics["tbt_ms"] = float(performance.tbt_ms)

        counts = await self._session.execute(
            sa.select(Finding.severity, sa.func.count())
            .where(Finding.scan_id == scan_id, Finding.status == FindingStatus.OPEN)
            .group_by(Finding.severity)
        )
        by_severity = {severity: int(total) for severity, total in counts}
        metrics["findings_open"] = float(sum(by_severity.values()))
        metrics["findings_critical"] = float(by_severity.get(Severity.CRITICAL, 0))
        metrics["findings_high"] = float(by_severity.get(Severity.HIGH, 0))

        return metrics

    # ── Dashboard ──────────────────────────────────────────────────────────

    async def dashboard(self) -> dict[str, Any]:
        """Resumen agregado para la portada (§28)."""
        projects = await self._session.scalar(
            sa.select(sa.func.count()).select_from(Project).where(self._owned())
        )
        sites = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(Site)
            .join(Project, Project.id == Site.project_id)
            .where(self._owned())
        )
        authorized = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(Site)
            .join(Project, Project.id == Site.project_id)
            .where(self._owned(), Site.authorized_by.is_not(None))
        )
        scans = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(Scan)
            .join(Site, Site.id == Scan.site_id)
            .join(Project, Project.id == Site.project_id)
            .where(self._owned())
        )
        running = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(Scan)
            .join(Site, Site.id == Scan.site_id)
            .join(Project, Project.id == Site.project_id)
            .where(self._owned(), Scan.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]))
        )

        severity_rows = await self._session.execute(
            sa.select(Finding.severity, sa.func.count())
            .join(Scan, Scan.id == Finding.scan_id)
            .join(Site, Site.id == Scan.site_id)
            .join(Project, Project.id == Site.project_id)
            .where(
                self._owned(),
                Finding.status == FindingStatus.OPEN,
                Scan.id.in_(self._latest_scan_ids()),
            )
            .group_by(Finding.severity)
        )
        by_severity = {severity.value: int(total) for severity, total in severity_rows}

        latest = await self._session.execute(
            sa.select(Scan, Site.name, Site.base_url)
            .join(Site, Site.id == Scan.site_id)
            .join(Project, Project.id == Site.project_id)
            .where(self._owned())
            .order_by(Scan.id.desc())
            .limit(5)
        )

        overall_rows = await self._session.execute(
            sa.select(Score.value)
            .join(Scan, Scan.id == Score.scan_id)
            .join(Site, Site.id == Scan.site_id)
            .join(Project, Project.id == Site.project_id)
            .where(
                self._owned(),
                Score.system == ScoreSystem.SOFTREE,
                Score.category == ScoreCategory.OVERALL,
                Scan.id.in_(self._latest_scan_ids()),
            )
        )
        values = [float(value) for (value,) in overall_rows if value is not None]

        return {
            "projects": int(projects or 0),
            "sites": int(sites or 0),
            "authorized_sites": int(authorized or 0),
            "scans": int(scans or 0),
            "scans_in_progress": int(running or 0),
            "average_score": round(sum(values) / len(values), 1) if values else None,
            "scored_sites": len(values),
            "open_findings_by_severity": {
                severity: by_severity.get(severity, 0)
                for severity in ("critical", "high", "medium", "low", "info")
            },
            "recent_scans": [
                {
                    "scan_id": scan.id,
                    "site_name": name,
                    "site_base_url": base_url,
                    "status": scan.status.value,
                    "scan_type": scan.scan_type.value,
                    "queued_at": scan.queued_at,
                    "finished_at": scan.finished_at,
                }
                for scan, name, base_url in latest
            ],
        }

    def _latest_scan_ids(self) -> sa.Select[tuple[uuid.UUID]]:
        """Subconsulta con el último scan terminado de cada sitio.

        El dashboard suma el estado **actual** de cada sitio; contar todos los
        scans multiplicaría los hallazgos por el número de auditorías.
        """
        # `DISTINCT ON` en lugar de `max(id)`: PostgreSQL no define `max` sobre
        # UUID, y los identificadores son UUID v7, ordenables por tiempo.
        return (
            sa.select(Scan.id)
            .distinct(Scan.site_id)
            .join(Site, Site.id == Scan.site_id)
            .join(Project, Project.id == Site.project_id)
            .where(self._owned(), Scan.status.in_(TERMINAL_WITH_DATA))
            .order_by(Scan.site_id, Scan.id.desc())
        )

    async def history(self, site_id: uuid.UUID, limit: int = 50) -> list[dict[str, Any]]:
        """Histórico de auditorías de un sitio con su score (§31)."""
        owned = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(Site)
            .join(Project, Project.id == Site.project_id)
            .where(Site.id == site_id, self._owned())
        )
        if not owned:
            raise NotFoundError("El sitio no existe.")

        overall = (
            sa.select(Score.value)
            .where(
                Score.scan_id == Scan.id,
                Score.system == ScoreSystem.SOFTREE,
                Score.category == ScoreCategory.OVERALL,
            )
            .correlate(Scan)
            .scalar_subquery()
        )
        open_findings = (
            sa.select(sa.func.count())
            .select_from(Finding)
            .where(Finding.scan_id == Scan.id, Finding.status == FindingStatus.OPEN)
            .correlate(Scan)
            .scalar_subquery()
        )

        rows = await self._session.execute(
            sa.select(Scan, overall.label("score"), open_findings.label("findings"))
            .where(Scan.site_id == site_id)
            .order_by(Scan.id.desc())
            .limit(limit)
        )

        return [
            {
                "scan_id": scan.id,
                "scan_type": scan.scan_type.value,
                "status": scan.status.value,
                "queued_at": scan.queued_at,
                "finished_at": scan.finished_at,
                "duration_ms": scan.duration_ms,
                "engine_version": scan.engine_version,
                "softree_overall": float(score) if score is not None else None,
                "open_findings": int(findings or 0),
            }
            for scan, score, findings in rows
        ]
