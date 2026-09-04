"""Servicio de reportes: generación, almacenamiento y descarga."""

from __future__ import annotations

import datetime as dt
import hashlib
import pathlib
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from softree_audit.core.config import Settings
from softree_audit.core.errors import AppError, NotFoundError
from softree_audit.core.logging import get_logger
from softree_audit.models import (
    Project,
    Report,
    ReportAudience,
    ReportFormat,
    Scan,
    ScanStatus,
    Site,
)
from softree_audit.reports.ai_service import AiAnalysisService
from softree_audit.services.reports.builder import ReportBuilder
from softree_audit.services.reports.model import ReportModel
from softree_audit.services.reports.renderer import render_html, render_json, render_pdf
from softree_audit.version import REPORT_VERSION

logger = get_logger(__name__)

EXTENSIONS = {
    ReportFormat.PDF: "pdf",
    ReportFormat.HTML: "html",
    ReportFormat.JSON: "json",
}

MEDIA_TYPES = {
    ReportFormat.PDF: "application/pdf",
    ReportFormat.HTML: "text/html; charset=utf-8",
    ReportFormat.JSON: "application/json",
}


class ScanNotFinishedError(AppError):
    status_code = 409
    code = "scan_not_finished"
    message = "La auditoría todavía no ha terminado; no puede generarse su reporte."


class ReportFileMissingError(AppError):
    status_code = 410
    code = "report_file_missing"
    message = "El archivo del reporte ya no está disponible. Vuelva a generarlo."


class ReportService:
    def __init__(
        self,
        session: AsyncSession,
        owner_id: uuid.UUID,
        reports_dir: str,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._owner_id = owner_id
        self._root = pathlib.Path(reports_dir)
        # Sin configuración de IA el reporte se genera igual, sin esa sección.
        self._ai = AiAnalysisService(session, settings) if settings is not None else None

    async def _owned_scan(self, scan_id: uuid.UUID) -> Scan:
        scan = (
            await self._session.execute(
                sa.select(Scan)
                .join(Site, Site.id == Scan.site_id)
                .join(Project, Project.id == Site.project_id)
                .where(Scan.id == scan_id, Project.owner_id == self._owner_id)
            )
        ).scalar_one_or_none()
        if scan is None:
            raise NotFoundError("La auditoría no existe.")
        return scan

    async def generate(
        self,
        scan_id: uuid.UUID,
        formats: list[ReportFormat],
        audience: ReportAudience = ReportAudience.COMBINED,
    ) -> list[Report]:
        """Genera los formatos pedidos a partir de un único modelo de datos."""
        scan = await self._owned_scan(scan_id)
        if scan.status in (ScanStatus.QUEUED, ScanStatus.RUNNING):
            raise ScanNotFinishedError()

        model = await ReportBuilder(self._session, self._owner_id).build(scan_id)
        if self._ai is not None:
            # Antes de renderizar: los tres formatos deben contener lo mismo.
            await self._ai.ensure(scan_id, model)
        generated: list[Report] = []

        for report_format in formats:
            payload = self._render(model, report_format, audience)
            path = self._write(scan_id, report_format, audience, payload)
            generated.append(await self._record(scan_id, report_format, audience, path, payload))

        await self._session.flush()
        logger.info(
            "report.generated",
            scan_id=str(scan_id),
            formats=[item.value for item in formats],
            audience=audience.value,
        )
        return generated

    @staticmethod
    def _render(model: ReportModel, report_format: ReportFormat, audience: ReportAudience) -> bytes:
        if report_format is ReportFormat.PDF:
            return render_pdf(model, audience)
        if report_format is ReportFormat.HTML:
            return render_html(model, audience).encode("utf-8")
        return render_json(model, audience)

    def _write(
        self,
        scan_id: uuid.UUID,
        report_format: ReportFormat,
        audience: ReportAudience,
        payload: bytes,
    ) -> pathlib.Path:
        """Un archivo por formato y audiencia.

        La audiencia forma parte del nombre: sin ella, generar la versión
        ejecutiva sobrescribiría el archivo de la técnica, y los dos registros
        de la base de datos apuntarían al mismo documento.
        """
        directory = self._root / str(scan_id)
        directory.mkdir(parents=True, exist_ok=True)
        name = f"softree-audit-{scan_id}-{audience.value}.{EXTENSIONS[report_format]}"
        path = directory / name
        path.write_bytes(payload)
        return path

    async def _record(
        self,
        scan_id: uuid.UUID,
        report_format: ReportFormat,
        audience: ReportAudience,
        path: pathlib.Path,
        payload: bytes,
    ) -> Report:
        existing = (
            await self._session.execute(
                sa.select(Report).where(
                    Report.scan_id == scan_id,
                    Report.format == report_format,
                    Report.audience == audience,
                    Report.report_version == REPORT_VERSION,
                )
            )
        ).scalar_one_or_none()

        checksum = hashlib.sha256(payload).hexdigest()
        if existing is not None:
            # Regenerar sustituye el archivo y su registro: no se acumulan
            # versiones idénticas del mismo reporte.
            existing.storage_path = str(path)
            existing.size_bytes = len(payload)
            existing.checksum_sha256 = checksum
            existing.generated_at = dt.datetime.now(dt.UTC)
            return existing

        report = Report(
            scan_id=scan_id,
            format=report_format,
            report_version=REPORT_VERSION,
            audience=audience,
            storage_path=str(path),
            size_bytes=len(payload),
            checksum_sha256=checksum,
            generated_at=dt.datetime.now(dt.UTC),
        )
        self._session.add(report)
        return report

    async def list(self, scan_id: uuid.UUID) -> list[Report]:
        await self._owned_scan(scan_id)
        rows = await self._session.execute(
            sa.select(Report).where(Report.scan_id == scan_id).order_by(Report.format)
        )
        return list(rows.scalars())

    async def read(
        self,
        scan_id: uuid.UUID,
        report_format: ReportFormat,
        audience: ReportAudience | None = None,
    ) -> tuple[bytes, Report]:
        """Lee un reporte ya generado.

        Sin audiencia se devuelve el más reciente de ese formato, que es lo que
        espera quien solo quiere «el PDF».
        """
        await self._owned_scan(scan_id)
        query = sa.select(Report).where(Report.scan_id == scan_id, Report.format == report_format)
        if audience is not None:
            query = query.where(Report.audience == audience)
        report = (
            await self._session.execute(query.order_by(Report.generated_at.desc()).limit(1))
        ).scalar_one_or_none()
        if report is None:
            raise NotFoundError("El reporte todavía no se ha generado.")

        path = pathlib.Path(report.storage_path)
        if not path.is_file():
            # El registro existe pero el archivo no: decirlo es mejor que un 500.
            logger.warning("report.file_missing", scan_id=str(scan_id), path=str(path))
            raise ReportFileMissingError()

        return path.read_bytes(), report
