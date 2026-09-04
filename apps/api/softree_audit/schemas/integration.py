"""Esquemas de integraciones externas."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Any

from pydantic import Field

from softree_audit.models.enums import SearchConsoleDimension, SearchConsolePeriod
from softree_audit.schemas.common import ApiModel


class GoogleConnectRequest(ApiModel):
    project_id: uuid.UUID


class GoogleConnectResponse(ApiModel):
    authorization_url: str
    state: str


class GoogleStatusResponse(ApiModel):
    project_id: uuid.UUID
    status: str = Field(
        description=(
            "`not_connected`, `connected`, `revoked` o `error`. No estar conectado no es un error."
        )
    )
    configured: bool = Field(description="Si la aplicación tiene credenciales de Google.")
    google_account_email: str | None
    property_url: str | None
    last_sync_at: dt.datetime | None
    last_error: str | None


class GoogleProperty(ApiModel):
    site_url: str
    permission_level: str


class GooglePropertySelection(ApiModel):
    project_id: uuid.UUID
    property_url: Annotated[str, Field(min_length=1, max_length=2048)]


class SearchConsoleMetricRead(ApiModel):
    period: SearchConsolePeriod
    dimension: SearchConsoleDimension
    dimension_value: str
    clicks: int
    impressions: int
    ctr: float
    position: float


class ScanSearchConsoleResponse(ApiModel):
    """Métricas de Search Console de una auditoría."""

    scan_id: uuid.UUID
    module_status: str
    module_detail: dict[str, Any] | None
    property_url: str | None
    totals: dict[str, Any]
    metrics: list[SearchConsoleMetricRead]
