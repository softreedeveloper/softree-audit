"""Orquestador del pipeline de scan.

Responsabilidades exclusivas del orquestador (`architecture.md` §3):
aplicar el timeout de cada módulo, capturar su excepción, registrar duración y
error, persistir los resultados y continuar con el siguiente módulo. Un módulo
que falla no cancela el scan completo.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import time
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from softree_audit.core.config import Settings
from softree_audit.core.logging import get_logger
from softree_audit.core.redis import RedisClient
from softree_audit.models import (
    Finding,
    FindingStatus,
    ModuleName,
    ModuleStatus,
    Page,
    PerformanceResult,
    Project,
    Scan,
    ScanModuleRun,
    ScanStatus,
    Score,
    ScoreCategory,
    ScoreSystem,
    SearchConsoleConnection,
    SearchConsoleMetric,
    SEOResult,
    Site,
)
from softree_audit.scans import cancellation
from softree_audit.scans.contracts import ModuleResult, ScanContext
from softree_audit.scans.modules import build_registry, module_timeout_seconds, modules_for
from softree_audit.scans.scoring_inputs import build_input
from softree_audit.scans.scoring_inputs import summary as scoring_summary
from softree_audit.scoring import compute as compute_score
from softree_audit.services.common.url_guard import ScopePolicy
from softree_audit.services.crawler.models import CrawlResult, PageData
from softree_audit.services.findings.models import NormalizedFinding
from softree_audit.services.performance.engine import PRIMARY_STRATEGY, PerformanceAnalysis
from softree_audit.services.search_console.sync import SearchConsoleAnalysis
from softree_audit.services.security.scanner import SecurityAnalysis
from softree_audit.services.seo.engine import SeoAnalysis
from softree_audit.version import SCAN_ENGINE_VERSION

logger = get_logger(__name__)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class ScanOrchestrator:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: RedisClient,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        self._settings = settings

    async def run(self, scan_id: uuid.UUID) -> ScanStatus:
        """Ejecuta el pipeline y garantiza que el scan llega a un estado final.

        Cualquier error no previsto del propio orquestador deja el scan en
        `failed`: quedarse en `running` indefinidamente sería peor que fallar.
        """
        try:
            return await self._run(scan_id)
        except Exception as exc:  # el scan nunca debe quedar sin estado terminal
            logger.exception("scan.orchestrator_failed", scan_id=str(scan_id))
            await self._force_failed(scan_id, f"{type(exc).__name__}: {exc}")
            return ScanStatus.FAILED

    async def _force_failed(self, scan_id: uuid.UUID, error: str) -> None:
        async with self._session_factory() as session:
            await session.execute(
                sa.update(Scan)
                .where(Scan.id == scan_id)
                .values(
                    status=ScanStatus.FAILED,
                    finished_at=utcnow(),
                    progress=100,
                    error=error[:4000],
                )
            )
            await session.execute(
                sa.update(ScanModuleRun)
                .where(
                    ScanModuleRun.scan_id == scan_id,
                    ScanModuleRun.status.in_([ModuleStatus.PENDING, ModuleStatus.RUNNING]),
                )
                .values(status=ModuleStatus.FAILED, finished_at=utcnow(), error=error[:4000])
            )
            await session.commit()
        await cancellation.clear_cancel(self._redis, scan_id)

    async def _run(self, scan_id: uuid.UUID) -> ScanStatus:
        """Pipeline propiamente dicho."""
        async with self._session_factory() as session:
            scan = await session.get(Scan, scan_id)
            if scan is None:
                logger.warning("scan.not_found", scan_id=str(scan_id))
                return ScanStatus.FAILED
            if scan.status is not ScanStatus.QUEUED:
                # Reentrega de la cola sobre un scan ya procesado.
                logger.info("scan.already_processed", scan_id=str(scan_id), status=scan.status)
                return scan.status

            base_url = str(scan.scope_snapshot.get("base_url", ""))
            scope = ScopePolicy.from_snapshot(scan.scope_snapshot)
            module_names = modules_for(scan.scan_type)

            scan.status = ScanStatus.RUNNING
            scan.started_at = utcnow()
            scan.progress = 0
            await self._create_module_rows(session, scan_id, module_names)
            await session.commit()

        context = ScanContext(
            scan_id=scan_id,
            site_id=scan.site_id,
            base_url=base_url,
            scope_snapshot=dict(scan.scope_snapshot),
            scope=scope,
            is_cancelled=lambda: cancellation.is_cancelled(self._redis, scan_id),
            redis=self._redis,
            search_console=await self._search_console_credentials(scan.site_id),
        )

        registry = build_registry(self._settings)
        outcomes: dict[ModuleName, ModuleStatus] = {}
        started_at = time.perf_counter()

        for index, name in enumerate(module_names, start=1):
            if await context.is_cancelled():
                await self._mark_remaining_skipped(scan_id, module_names, outcomes, "cancelled")
                return await self._finalize(scan_id, ScanStatus.CANCELLED, outcomes, started_at)

            status = await self._run_module(registry, name, context)
            outcomes[name] = status
            await self._update_progress(scan_id, int(index / len(module_names) * 100))

        if await context.is_cancelled():
            return await self._finalize(scan_id, ScanStatus.CANCELLED, outcomes, started_at)

        # El scoring cierra el pipeline: necesita todo lo anterior ya persistido.
        await self._score(scan_id, context)

        return await self._finalize(scan_id, self._final_status(outcomes), outcomes, started_at)

    # ── Scoring ────────────────────────────────────────────────────────────

    async def _score(self, scan_id: uuid.UUID, context: ScanContext) -> None:
        """Calcula y persiste el Softree Score con lo que el scan produjo.

        Un fallo aquí no debe invalidar la auditoría: los datos ya están
        guardados y el score puede recalcularse.
        """
        try:
            seo_artifact = context.artifact(ModuleName.SEO)
            performance_artifact = context.artifact(ModuleName.PERFORMANCE)
            security_artifact = context.artifact(ModuleName.SECURITY)

            findings: list[NormalizedFinding] = []
            if isinstance(seo_artifact, SeoAnalysis):
                findings.extend(seo_artifact.findings)
            if isinstance(security_artifact, SecurityAnalysis):
                findings.extend(security_artifact.findings)
            if isinstance(performance_artifact, PerformanceAnalysis):
                findings.extend(performance_artifact.findings)

            if not findings and not isinstance(seo_artifact, SeoAnalysis):
                logger.info("scoring.skipped", scan_id=str(scan_id), reason="sin_datos")
                return

            statuses = await self._finding_statuses(scan_id)
            score_input = build_input(
                findings=findings,
                statuses=statuses,
                aggregates=seo_artifact.aggregates
                if isinstance(seo_artifact, SeoAnalysis)
                else None,
                performance=(
                    performance_artifact.results
                    if isinstance(performance_artifact, PerformanceAnalysis)
                    else []
                ),
                weights=self._settings.effective_scoring_weights,
            )
            breakdown = compute_score(score_input)
            await self._persist_scores(scan_id, breakdown)
            logger.info("scoring.completed", scan_id=str(scan_id), **scoring_summary(breakdown))
        except Exception:  # el score es derivado: su fallo no invalida el scan
            logger.exception("scoring.failed", scan_id=str(scan_id))

    async def _carried_statuses(
        self, scan_id: uuid.UUID, findings: list[NormalizedFinding]
    ) -> dict[str, FindingStatus]:
        """Estados que se heredan del scan anterior del mismo sitio.

        Solo se arrastran `accepted` y `false_positive`, que son decisiones
        humanas sobre el hallazgo. `fixed` no se hereda: si el problema vuelve a
        detectarse es que no está corregido.
        """
        if not findings:
            return {}
        fingerprints = [finding.fingerprint for finding in findings]

        async with self._session_factory() as session:
            site_id = await session.scalar(sa.select(Scan.site_id).where(Scan.id == scan_id))
            if site_id is None:
                return {}

            rows = await session.execute(
                sa.select(Finding.fingerprint, Finding.status, Finding.scan_id)
                .join(Scan, Scan.id == Finding.scan_id)
                .where(
                    Scan.site_id == site_id,
                    Scan.id != scan_id,
                    Finding.fingerprint.in_(fingerprints),
                    Finding.status.in_([FindingStatus.ACCEPTED, FindingStatus.FALSE_POSITIVE]),
                )
                .order_by(Finding.scan_id.desc())
            )

        carried: dict[str, FindingStatus] = {}
        for fingerprint, status, _ in rows:
            # El primero es el del scan más reciente.
            carried.setdefault(fingerprint, status)
        if carried:
            logger.info("findings.status_carried", scan_id=str(scan_id), inherited=len(carried))
        return carried

    async def _finding_statuses(self, scan_id: uuid.UUID) -> dict[str, FindingStatus]:
        """Estado actual de los findings del scan, por huella."""
        async with self._session_factory() as session:
            rows = await session.execute(
                sa.select(Finding.fingerprint, Finding.status).where(Finding.scan_id == scan_id)
            )
            return dict(rows.tuples().all())

    async def _persist_scores(self, scan_id: uuid.UUID, breakdown: Any) -> None:
        async with self._session_factory() as session:
            for category, value in breakdown.categories.items():
                session.add(
                    Score(
                        scan_id=scan_id,
                        system=ScoreSystem.SOFTREE,
                        category=ScoreCategory(category),
                        value=value,
                        weight=breakdown.applied_weights.get(category),
                        detail=dict(breakdown.detail.get(category, {})),
                        engine_version=SCAN_ENGINE_VERSION,
                    )
                )
            if breakdown.overall is not None:
                session.add(
                    Score(
                        scan_id=scan_id,
                        system=ScoreSystem.SOFTREE,
                        category=ScoreCategory.OVERALL,
                        value=breakdown.overall,
                        detail={
                            "band": breakdown.band,
                            "applied_weights": breakdown.applied_weights,
                        },
                        engine_version=SCAN_ENGINE_VERSION,
                    )
                )
            await session.commit()

    # ── Ejecución de un módulo ─────────────────────────────────────────────

    async def _run_module(
        self,
        registry: dict[ModuleName, Any],
        name: ModuleName,
        context: ScanContext,
    ) -> ModuleStatus:
        module = registry.get(name)
        if module is None:
            await self._store_module(
                context.scan_id, name, ModuleStatus.SKIPPED, 0, None, {"reason": "not_registered"}
            )
            return ModuleStatus.SKIPPED

        await self._store_module(context.scan_id, name, ModuleStatus.RUNNING, None, None, None)
        started = time.perf_counter()

        timeout = module_timeout_seconds(name, self._settings)

        try:
            async with asyncio.timeout(timeout):
                result: ModuleResult = await module.run(context)
                # La persistencia forma parte del módulo: si falla, el módulo
                # falla, pero el scan continúa y termina en un estado definido.
                await self._persist_artifact(context.scan_id, name, result.artifact)
        except TimeoutError:
            duration_ms = int((time.perf_counter() - started) * 1000)
            message = f"El módulo superó su tiempo máximo de {int(timeout)} s."
            logger.warning(
                "scan.module_timeout",
                scan_id=str(context.scan_id),
                module=name.value,
                status=ModuleStatus.FAILED.value,
                duration_ms=duration_ms,
                error=message,
            )
            await self._store_module(
                context.scan_id, name, ModuleStatus.FAILED, duration_ms, message, None
            )
            return ModuleStatus.FAILED
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            message = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "scan.module_failed",
                scan_id=str(context.scan_id),
                module=name.value,
                status=ModuleStatus.FAILED.value,
                duration_ms=duration_ms,
                error=message,
            )
            await self._store_module(
                context.scan_id, name, ModuleStatus.FAILED, duration_ms, message, None
            )
            return ModuleStatus.FAILED

        duration_ms = int((time.perf_counter() - started) * 1000)
        status = ModuleStatus.SKIPPED if result.skipped else ModuleStatus.COMPLETED
        detail = dict(result.detail)
        if result.skip_reason:
            detail["reason"] = result.skip_reason

        if result.artifact is not None:
            context.artifacts[name.value] = result.artifact

        logger.info(
            "scan.module_completed",
            scan_id=str(context.scan_id),
            module=name.value,
            status=status.value,
            duration_ms=duration_ms,
            error=None,
        )
        await self._store_module(context.scan_id, name, status, duration_ms, None, detail)
        return status

    async def _persist_artifact(self, scan_id: uuid.UUID, name: ModuleName, artifact: Any) -> None:
        if name is ModuleName.SEO and isinstance(artifact, SeoAnalysis):
            await self._persist_seo(scan_id, artifact)
            return

        if name is ModuleName.SECURITY and isinstance(artifact, SecurityAnalysis):
            await self._persist_findings(scan_id, artifact.findings)
            return

        if name is ModuleName.PERFORMANCE and isinstance(artifact, PerformanceAnalysis):
            await self._persist_performance(scan_id, artifact)
            return

        if name is ModuleName.SEARCH_CONSOLE and isinstance(artifact, SearchConsoleAnalysis):
            await self._persist_search_console(scan_id, artifact)
            return

        if name is not ModuleName.CRAWLER or not isinstance(artifact, CrawlResult):
            return

        # Defensa en profundidad: el crawler ya deduplica, pero dos rutas que
        # terminan en el mismo destino tras una redirección producirían la misma
        # clave `(scan_id, url_hash)` y romperían la inserción completa.
        seen: set[bytes] = set()
        async with self._session_factory() as session:
            for page in artifact.pages:
                row = self._to_page_row(scan_id, page)
                if row.url_hash in seen:
                    logger.info("scan.duplicate_page_skipped", scan_id=str(scan_id), url=page.url)
                    continue
                seen.add(row.url_hash)
                session.add(row)
            await session.commit()

    async def _persist_seo(self, scan_id: uuid.UUID, analysis: SeoAnalysis) -> None:
        """Guarda los agregados SEO y los findings normalizados del scan."""
        async with self._session_factory() as session:
            session.add(SEOResult(scan_id=scan_id, **analysis.aggregates.as_dict()))
            await session.commit()
        await self._persist_findings(scan_id, analysis.findings)

    async def _persist_performance(self, scan_id: uuid.UUID, analysis: PerformanceAnalysis) -> None:
        """Guarda las medidas, las puntuaciones de Google y los findings.

        Las puntuaciones de Lighthouse se persisten con `system = google`, sin
        transformar: nunca deben confundirse con el Softree Score (§27).
        """
        async with self._session_factory() as session:
            for result in analysis.results:
                session.add(PerformanceResult(scan_id=scan_id, **result.as_row()))

            # La estrategia principal es la que representa al sitio en el
            # cuadro de mando; la otra queda en `detail` para poder consultarla.
            by_category: dict[str, dict[str, int]] = {}
            for score in analysis.google_scores:
                by_category.setdefault(score.category.value, {})[score.strategy.value] = score.value

            for category, values in by_category.items():
                primary = values.get(PRIMARY_STRATEGY.value)
                value = primary if primary is not None else next(iter(values.values()))
                session.add(
                    Score(
                        scan_id=scan_id,
                        system=ScoreSystem.GOOGLE,
                        category=ScoreCategory(category),
                        value=value,
                        detail={"by_strategy": values, "primary": PRIMARY_STRATEGY.value},
                        engine_version=SCAN_ENGINE_VERSION,
                    )
                )
            await session.commit()

        await self._persist_findings(scan_id, analysis.findings)

    async def _search_console_credentials(
        self, site_id: uuid.UUID
    ) -> tuple[str, str | None] | None:
        """Resuelve la credencial de Search Console del proyecto del sitio.

        Se hace aquí y no en el módulo porque exige acceso a base de datos, que
        los módulos no tienen por contrato. Si no hay conexión, o si Google la
        rechaza, se devuelve `None` y el módulo se limita a omitirse.
        """
        from softree_audit.integrations.google import GoogleIntegrationService
        from softree_audit.models import ConnectionStatus

        async with self._session_factory() as session:
            row = (
                await session.execute(
                    sa.select(SearchConsoleConnection, Project.owner_id)
                    .join(Project, Project.id == SearchConsoleConnection.project_id)
                    .join(Site, Site.project_id == Project.id)
                    .where(Site.id == site_id)
                )
            ).first()

            if row is None:
                return None
            connection, owner_id = row
            if connection.status is not ConnectionStatus.CONNECTED:
                return None

            service = GoogleIntegrationService(session, self._redis, self._settings, owner_id)
            try:
                access_token = await service.access_token_for(connection.project_id)
            except Exception as exc:
                logger.info(
                    "search_console.credentials_unavailable",
                    site_id=str(site_id),
                    error=type(exc).__name__,
                )
                await session.commit()
                return None
            await session.commit()

        return access_token, connection.property_url

    async def _persist_search_console(
        self, scan_id: uuid.UUID, analysis: SearchConsoleAnalysis
    ) -> None:
        """Guarda las métricas, sin repetir la clave `(periodo, dimensión, valor)`."""
        seen: set[tuple[str, str, str]] = set()
        async with self._session_factory() as session:
            for metric in analysis.metrics:
                key = (
                    metric.period.value,
                    metric.row.dimension.value,
                    metric.row.dimension_value,
                )
                if key in seen:
                    continue
                seen.add(key)
                session.add(
                    SearchConsoleMetric(
                        scan_id=scan_id,
                        period=metric.period,
                        dimension=metric.row.dimension,
                        dimension_value=metric.row.dimension_value,
                        clicks=metric.row.clicks,
                        impressions=metric.row.impressions,
                        ctr=round(metric.row.ctr, 6),
                        position=round(metric.row.position, 2),
                    )
                )
            await session.commit()

    async def _persist_findings(
        self, scan_id: uuid.UUID, findings: list[NormalizedFinding]
    ) -> None:
        """Guarda findings ya normalizados, sin repetir huellas.

        El índice único `(scan_id, fingerprint)` implementa la deduplicación en
        base de datos; aquí se filtra antes para que una colisión no aborte la
        inserción completa del módulo.
        """
        carried = await self._carried_statuses(scan_id, findings)
        seen: set[str] = set()
        async with self._session_factory() as session:
            for finding in findings:
                fingerprint = finding.fingerprint
                if fingerprint in seen:
                    logger.info(
                        "scan.duplicate_finding_skipped",
                        scan_id=str(scan_id),
                        rule_id=finding.rule_id,
                    )
                    continue
                seen.add(fingerprint)
                row = self._to_finding_row(scan_id, finding)
                # Un hallazgo aceptado o marcado como falso positivo en un scan
                # anterior del mismo sitio no vuelve a aparecer como abierto:
                # obligaría a repetir la misma decisión en cada auditoría.
                inherited = carried.get(fingerprint)
                if inherited is not None:
                    row.status = inherited
                session.add(row)
            await session.commit()

    @staticmethod
    def _to_finding_row(scan_id: uuid.UUID, finding: NormalizedFinding) -> Finding:
        return Finding(
            scan_id=scan_id,
            source=finding.source,
            category=finding.category,
            rule_id=finding.rule_id,
            title=finding.title,
            severity=finding.severity,
            confidence=finding.confidence,
            url=finding.url,
            parameter=finding.parameter,
            evidence=finding.evidence,
            description=finding.description,
            impact=finding.impact,
            remediation=finding.remediation,
            client_explanation=finding.client_explanation,
            cwe=finding.cwe,
            owasp=finding.owasp,
            references=finding.references,
            occurrences=finding.occurrences,
            fingerprint=finding.fingerprint,
            raw=finding.raw,
        )

    @staticmethod
    def _to_page_row(scan_id: uuid.UUID, page: PageData) -> Page:
        return Page(
            scan_id=scan_id,
            url=page.url,
            url_hash=hashlib.sha256(page.url.encode("utf-8")).digest(),
            depth=page.depth,
            discovered_from=page.discovered_from,
            status_code=page.status_code,
            content_type=page.content_type,
            response_time_ms=page.response_time_ms,
            content_length=page.content_length,
            title=page.title,
            meta_description=page.meta_description,
            canonical=page.canonical,
            meta_robots=page.meta_robots,
            h1=page.h1,
            h2=page.h2,
            internal_links=page.internal_links,
            external_links=page.external_links,
            images_total=page.images_total,
            images_missing_alt=page.images_missing_alt,
            scripts_total=page.scripts_total,
            forms_total=page.forms_total,
            redirect_chain=page.redirect_chain,
            structured_data=page.structured_data,
            is_indexable=page.is_indexable,
            error=page.error,
        )

    # ── Persistencia de estado ─────────────────────────────────────────────

    async def _create_module_rows(
        self, session: AsyncSession, scan_id: uuid.UUID, names: tuple[ModuleName, ...]
    ) -> None:
        for name in names:
            session.add(ScanModuleRun(scan_id=scan_id, module=name, status=ModuleStatus.PENDING))

    async def _store_module(
        self,
        scan_id: uuid.UUID,
        name: ModuleName,
        status: ModuleStatus,
        duration_ms: int | None,
        error: str | None,
        detail: dict[str, Any] | None,
    ) -> None:
        values: dict[str, Any] = {"status": status}
        if status is ModuleStatus.RUNNING:
            values["started_at"] = utcnow()
        else:
            values["finished_at"] = utcnow()
        if duration_ms is not None:
            values["duration_ms"] = duration_ms
        if error is not None:
            values["error"] = error[:4000]
        if detail is not None:
            values["detail"] = detail

        async with self._session_factory() as session:
            await session.execute(
                sa.update(ScanModuleRun)
                .where(ScanModuleRun.scan_id == scan_id, ScanModuleRun.module == name)
                .values(**values)
            )
            await session.commit()

    async def _mark_remaining_skipped(
        self,
        scan_id: uuid.UUID,
        names: tuple[ModuleName, ...],
        outcomes: dict[ModuleName, ModuleStatus],
        reason: str,
    ) -> None:
        for name in names:
            if name in outcomes:
                continue
            outcomes[name] = ModuleStatus.SKIPPED
            await self._store_module(
                scan_id, name, ModuleStatus.SKIPPED, 0, None, {"reason": reason}
            )

    async def _update_progress(self, scan_id: uuid.UUID, progress: int) -> None:
        async with self._session_factory() as session:
            await session.execute(
                sa.update(Scan)
                .where(Scan.id == scan_id)
                .values(progress=min(max(progress, 0), 100))
            )
            await session.commit()

    @staticmethod
    def _final_status(outcomes: dict[ModuleName, ModuleStatus]) -> ScanStatus:
        """Reglas de transición de `docs/spec/architecture.md` §4."""
        completed = sum(1 for status in outcomes.values() if status is ModuleStatus.COMPLETED)
        failed = sum(1 for status in outcomes.values() if status is ModuleStatus.FAILED)

        if failed and completed:
            return ScanStatus.PARTIAL
        if failed and not completed:
            return ScanStatus.FAILED
        return ScanStatus.COMPLETED

    async def _finalize(
        self,
        scan_id: uuid.UUID,
        status: ScanStatus,
        outcomes: dict[ModuleName, ModuleStatus],
        started_at: float,
    ) -> ScanStatus:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        failures = [name.value for name, value in outcomes.items() if value is ModuleStatus.FAILED]

        async with self._session_factory() as session:
            await session.execute(
                sa.update(Scan)
                .where(Scan.id == scan_id)
                .values(
                    status=status,
                    finished_at=utcnow(),
                    duration_ms=duration_ms,
                    progress=100,
                    error=("Módulos con error: " + ", ".join(failures)) if failures else None,
                )
            )
            await session.commit()

        await cancellation.clear_cancel(self._redis, scan_id)
        logger.info(
            "scan.finished",
            scan_id=str(scan_id),
            status=status.value,
            duration_ms=duration_ms,
            error=", ".join(failures) or None,
        )
        return status
