"""Endpoints de reportes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from softree_audit.api.deps import AppSettings, CurrentUser, DbSession, Limiter, client_ip
from softree_audit.core import rate_limit
from softree_audit.models.enums import ReportAudience, ReportFormat
from softree_audit.reports.service import MEDIA_TYPES, ReportService
from softree_audit.schemas.common import ErrorResponse
from softree_audit.schemas.report import ReportGenerateRequest, ReportRead

router = APIRouter(prefix="/reports", tags=["reports"])

NOT_FOUND: dict[int | str, dict[str, object]] = {
    404: {"model": ErrorResponse, "description": "La auditoría o el reporte no existen"}
}


def get_service(session: DbSession, user: CurrentUser, settings: AppSettings) -> ReportService:
    return ReportService(session, user.id, settings.reports_dir)


ServiceDep = Annotated[ReportService, Depends(get_service)]


@router.post(
    "/{scan_id}/generate",
    response_model=list[ReportRead],
    status_code=status.HTTP_201_CREATED,
    summary="Generar el reporte de una auditoría",
    responses={
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "La auditoría no ha terminado"},
        429: {"model": ErrorResponse, "description": "Demasiadas generaciones"},
    },
)
async def generate_report(
    scan_id: uuid.UUID,
    service: ServiceDep,
    limiter: Limiter,
    ip: Annotated[str, Depends(client_ip)],
    payload: ReportGenerateRequest | None = None,
) -> list[ReportRead]:
    await limiter.check(rate_limit.REPORT_GENERATE, ip)
    request = payload or ReportGenerateRequest()
    reports = await service.generate(scan_id, request.formats, request.audience)
    return [ReportRead.model_validate(report) for report in reports]


@router.get(
    "/{scan_id}",
    response_model=list[ReportRead],
    summary="Reportes generados de una auditoría",
    responses=NOT_FOUND,
)
async def list_reports(scan_id: uuid.UUID, service: ServiceDep) -> list[ReportRead]:
    return [ReportRead.model_validate(report) for report in await service.list(scan_id)]


@router.get(
    "/{scan_id}/download",
    summary="Descargar un reporte",
    responses={
        **NOT_FOUND,
        410: {"model": ErrorResponse, "description": "El archivo ya no está disponible"},
    },
    response_class=Response,
)
async def download_report(
    scan_id: uuid.UUID,
    service: ServiceDep,
    request: Request,
    report_format: Annotated[ReportFormat, Query(alias="format")] = ReportFormat.PDF,
    audience: Annotated[ReportAudience | None, Query()] = None,
) -> Response:
    payload, report = await service.read(scan_id, report_format, audience)
    extension = report.storage_path.rsplit(".", 1)[-1]
    filename = f"softree-audit-{scan_id}-{report.audience.value}.{extension}"

    return Response(
        content=payload,
        media_type=MEDIA_TYPES[report_format],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Report-Version": report.report_version,
            "X-Report-Audience": report.audience.value,
            "X-Report-Checksum": report.checksum_sha256 or "",
        },
    )
