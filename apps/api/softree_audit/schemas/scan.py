"""Esquemas de auditorías."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import Field

from softree_audit.models.enums import ModuleName, ModuleStatus, ScanStatus, ScanType
from softree_audit.schemas.common import ApiModel


class ScanCreate(ApiModel):
    site_id: uuid.UUID
    scan_type: ScanType = ScanType.FULL


class ScanModuleRead(ApiModel):
    module: ModuleName
    status: ModuleStatus
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
    duration_ms: int | None
    error: str | None
    detail: dict[str, Any] | None


class ScanRead(ApiModel):
    id: uuid.UUID
    site_id: uuid.UUID
    scan_type: ScanType
    status: ScanStatus
    progress: int
    queued_at: dt.datetime
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
    duration_ms: int | None
    error: str | None
    engine_version: str
    app_version: str
    site_name: str = ""
    site_base_url: str = ""
    pages_count: int = 0


class ScanDetail(ScanRead):
    modules: list[ScanModuleRead] = Field(default_factory=list)
    scope_snapshot: dict[str, Any]


class PageRead(ApiModel):
    id: uuid.UUID
    url: str
    depth: int
    discovered_from: str | None
    status_code: int | None
    content_type: str | None
    response_time_ms: int | None
    content_length: int | None
    title: str | None
    meta_description: str | None
    canonical: str | None
    meta_robots: str | None
    h1: list[str]
    h2: list[str]
    internal_links: int
    external_links: int
    images_total: int
    images_missing_alt: int
    scripts_total: int
    forms_total: int
    redirect_chain: list[Any]
    structured_data: dict[str, Any]
    is_indexable: bool | None
    error: str | None
