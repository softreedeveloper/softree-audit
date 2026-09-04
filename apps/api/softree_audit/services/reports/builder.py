"""Construcción del modelo del reporte a partir de los datos del scan."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from softree_audit.comparison.service import ComparisonService, NoPreviousScanError
from softree_audit.core.errors import NotFoundError
from softree_audit.models import (
    AiAnalysis,
    Finding,
    FindingSource,
    FindingStatus,
    ModuleName,
    PerformanceResult,
    Project,
    Scan,
    ScanModuleRun,
    Score,
    ScoreCategory,
    ScoreSystem,
    SEOResult,
    Severity,
    Site,
)
from softree_audit.services.reports.model import (
    AiRecommendationBlock,
    ReportAnalysis,
    ReportComparison,
    ReportFinding,
    ReportModel,
    ReportSection,
)
from softree_audit.version import APP_VERSION, REPORT_VERSION, SCAN_ENGINE_VERSION

SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}

SECTION_SOURCES: tuple[tuple[str, str, ModuleName, tuple[FindingSource, ...]], ...] = (
    ("security", "Seguridad", ModuleName.SECURITY, (FindingSource.ZAP,)),
    ("seo", "SEO", ModuleName.SEO, (FindingSource.SEO,)),
    ("performance", "Rendimiento", ModuleName.PERFORMANCE, (FindingSource.PAGESPEED,)),
    (
        "search_console",
        "Search Console",
        ModuleName.SEARCH_CONSOLE,
        (FindingSource.SEARCH_CONSOLE,),
    ),
)

# Cuántos hallazgos se destacan en la sección de recomendaciones.
MAX_RECOMMENDATIONS = 10


class ReportBuilder:
    def __init__(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        self._session = session
        self._owner_id = owner_id

    async def build(self, scan_id: uuid.UUID) -> ReportModel:
        row = (
            await self._session.execute(
                sa.select(Scan, Site, Project)
                .join(Site, Site.id == Scan.site_id)
                .join(Project, Project.id == Site.project_id)
                .where(Scan.id == scan_id, Project.owner_id == self._owner_id)
            )
        ).first()
        if row is None:
            raise NotFoundError("La auditoría no existe.")
        scan, site, project = row

        findings = list(
            (
                await self._session.execute(
                    sa.select(Finding).where(
                        Finding.scan_id == scan_id, Finding.status == FindingStatus.OPEN
                    )
                )
            ).scalars()
        )
        findings.sort(key=lambda item: (SEVERITY_ORDER[item.severity], -item.occurrences))

        modules = {
            module.module: module
            for module in (
                await self._session.execute(
                    sa.select(ScanModuleRun).where(ScanModuleRun.scan_id == scan_id)
                )
            ).scalars()
        }

        model = ReportModel(
            scan_id=str(scan.id),
            site_name=site.name,
            site_base_url=site.base_url,
            project_name=project.name,
            client_name=project.client_name,
            generated_at=dt.datetime.now(dt.UTC),
            period_start=scan.started_at,
            period_end=scan.finished_at,
            app_version=APP_VERSION,
            engine_version=scan.engine_version or SCAN_ENGINE_VERSION,
            report_version=REPORT_VERSION,
            softree_overall=None,
            band=None,
            scan_duration_ms=scan.duration_ms,
        )

        await self._fill_scores(scan_id, model)
        model.findings_by_severity = _severity_counts(findings)
        model.modules = [
            {
                "module": name.value,
                "status": module.status.value,
                "duration_ms": module.duration_ms,
                "error": module.error,
                "detail": module.detail,
            }
            for name, module in sorted(modules.items(), key=lambda item: item[0].value)
        ]

        await self._fill_sections(scan_id, findings, modules, model)
        model.recommendations = [
            _to_report_finding(item) for item in findings[:MAX_RECOMMENDATIONS]
        ]
        await self._fill_comparison(scan_id, model)
        await self._fill_ai_analysis(scan_id, model)
        return model

    # ── Partes ─────────────────────────────────────────────────────────────

    async def _fill_ai_analysis(self, scan_id: uuid.UUID, model: ReportModel) -> None:
        """Incorpora el análisis ya almacenado, si lo hay.

        El builder no llama al modelo de lenguaje: solo lee lo persistido, de
        modo que regenerar un formato no vuelva a pagar la llamada ni cambie el
        texto de un reporte ya entregado.
        """
        analysis = await self._session.scalar(
            sa.select(AiAnalysis).where(AiAnalysis.scan_id == scan_id)
        )
        if analysis is None:
            return

        model.ai_analysis = ReportAnalysis(
            summary=analysis.summary,
            recommendations=[
                AiRecommendationBlock(
                    title=str(item.get("title", "")),
                    detail=str(item.get("detail", "")),
                    priority=str(item.get("priority", "media")),
                )
                for item in analysis.recommendations
                if isinstance(item, dict)
            ],
            risks=[str(item) for item in analysis.risks],
            model=analysis.model,
            generated_at=analysis.generated_at,
        )

    async def _fill_scores(self, scan_id: uuid.UUID, model: ReportModel) -> None:
        rows = (
            await self._session.execute(sa.select(Score).where(Score.scan_id == scan_id))
        ).scalars()

        for score in rows:
            if score.value is None:
                continue
            value = float(score.value)
            if score.system is ScoreSystem.GOOGLE:
                model.google_scores[score.category.value] = value
            elif score.category is ScoreCategory.OVERALL:
                model.softree_overall = value
                band = score.detail.get("band")
                model.band = str(band) if band else None
            else:
                model.softree_categories[score.category.value] = value
                if score.weight is not None:
                    model.applied_weights[score.category.value] = float(score.weight)

    async def _fill_sections(
        self,
        scan_id: uuid.UUID,
        findings: list[Finding],
        modules: dict[ModuleName, ScanModuleRun],
        model: ReportModel,
    ) -> None:
        seo_result = (
            await self._session.execute(sa.select(SEOResult).where(SEOResult.scan_id == scan_id))
        ).scalar_one_or_none()
        if seo_result is not None:
            model.pages_crawled = seo_result.pages_crawled
            model.urls_discovered = seo_result.urls_discovered

        performance = list(
            (
                await self._session.execute(
                    sa.select(PerformanceResult).where(PerformanceResult.scan_id == scan_id)
                )
            ).scalars()
        )

        for key, title, module_name, sources in SECTION_SOURCES:
            module = modules.get(module_name)
            status = module.status.value if module is not None else "no_ejecutado"
            section = ReportSection(
                key=key,
                title=title,
                module_status=status,
                findings=[_to_report_finding(item) for item in findings if item.source in sources],
            )

            if status != "completed":
                reason = None
                if module is not None and isinstance(module.detail, dict):
                    reason = module.detail.get("reason")
                section.note = _module_note(status, reason)

            if key == "seo" and seo_result is not None:
                section.summary = {
                    "pages_crawled": seo_result.pages_crawled,
                    "urls_discovered": seo_result.urls_discovered,
                    "missing_title": seo_result.missing_title,
                    "duplicate_title": seo_result.duplicate_title,
                    "missing_description": seo_result.missing_description,
                    "missing_h1": seo_result.missing_h1,
                    "images_missing_alt": seo_result.images_missing_alt,
                    "broken_internal_links": seo_result.broken_internal_links,
                    "robots_txt_found": seo_result.robots_txt_found,
                    "sitemap_found": seo_result.sitemap_found,
                }
            if key == "performance" and performance:
                section.summary = {
                    result.strategy.value: {
                        "performance": result.performance_score,
                        "accessibility": result.accessibility_score,
                        "best_practices": result.best_practices_score,
                        "seo": result.seo_score,
                        "lcp_ms": result.lcp_ms,
                        "cls": float(result.cls) if result.cls is not None else None,
                        "inp_ms": result.inp_ms,
                        "tbt_ms": result.tbt_ms,
                        "has_field_data": result.has_field_data,
                    }
                    for result in performance
                }
            if key == "security" and module is not None and isinstance(module.detail, dict):
                section.summary = {
                    "urls_analyzed": module.detail.get("urls_submitted"),
                    "alerts_received": module.detail.get("alerts_received"),
                    "active_scan": module.detail.get("active_scan", False),
                }
            if key == "search_console" and module is not None and isinstance(module.detail, dict):
                section.summary = {
                    "property_url": module.detail.get("property_url"),
                    "totals": module.detail.get("totals", {}),
                }

            model.sections.append(section)

        # Accesibilidad y buenas prácticas tienen su propia sección porque son
        # categorías del score, aunque sus hallazgos vengan de otras fuentes.
        for key, title, category in (
            ("accessibility", "Accesibilidad", "accessibility"),
            ("best_practices", "Buenas prácticas", "best_practices"),
        ):
            selected = [item for item in findings if item.category.value == category]
            model.sections.append(
                ReportSection(
                    key=key,
                    title=title,
                    module_status="completed" if selected else "sin_hallazgos",
                    findings=[_to_report_finding(item) for item in selected],
                    summary={
                        "score": model.softree_categories.get(category),
                        "google_score": model.google_scores.get(category),
                    },
                )
            )

    async def _fill_comparison(self, scan_id: uuid.UUID, model: ReportModel) -> None:
        service = ComparisonService(self._session, self._owner_id)
        try:
            data = await service.compare(scan_id)
        except (NoPreviousScanError, NotFoundError):
            # La primera auditoría de un sitio no tiene con qué compararse.
            return

        model.comparison = ReportComparison(
            previous_scan_id=str(data["previous"]["scan_id"]),
            previous_finished_at=data["previous"]["finished_at"],
            counts=data["counts"],
            metrics=[
                metric for metric in data["metrics"] if metric["direction"] in ("mejora", "empeora")
            ],
            compared_sources=data["compared_sources"],
            sources_only_in_previous=data["sources_only_in_previous"],
        )


def _module_note(status: str, reason: Any) -> str:
    notes = {
        "skipped": "Este módulo no se ejecutó en esta auditoría.",
        "failed": "Este módulo falló durante la auditoría.",
        "no_ejecutado": "Este módulo no forma parte de esta auditoría.",
        "pending": "Este módulo no llegó a ejecutarse.",
    }
    base = notes.get(status, "Este módulo no produjo resultados.")
    if reason:
        base = f"{base} Motivo: {reason}."
    return f"{base} La ausencia de hallazgos no significa que no existan problemas."


def _severity_counts(findings: list[Finding]) -> dict[str, int]:
    counts = dict.fromkeys(("critical", "high", "medium", "low", "info"), 0)
    for finding in findings:
        counts[finding.severity.value] += 1
    return counts


def _to_report_finding(finding: Finding) -> ReportFinding:
    return ReportFinding(
        rule_id=finding.rule_id,
        title=finding.title,
        severity=finding.severity.value,
        confidence=finding.confidence.value,
        category=finding.category.value,
        source=finding.source.value,
        url=finding.url,
        occurrences=finding.occurrences,
        description=finding.description,
        impact=finding.impact,
        remediation=finding.remediation,
        client_explanation=finding.client_explanation,
        evidence=finding.evidence,
        cwe=finding.cwe,
        owasp=finding.owasp,
    )
