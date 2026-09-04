"""Esquemas de reportes."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import Field, field_validator

from softree_audit.models.enums import ReportAudience, ReportFormat
from softree_audit.schemas.common import ApiModel


class ReportGenerateRequest(ApiModel):
    formats: list[ReportFormat] = Field(
        default_factory=lambda: [ReportFormat.PDF, ReportFormat.HTML, ReportFormat.JSON]
    )
    audience: ReportAudience = ReportAudience.COMBINED

    @field_validator("formats")
    @classmethod
    def _unique_non_empty(cls, value: list[ReportFormat]) -> list[ReportFormat]:
        if not value:
            raise ValueError("Debe indicarse al menos un formato")
        seen: list[ReportFormat] = []
        for item in value:
            if item not in seen:
                seen.append(item)
        return seen


class ReportRead(ApiModel):
    id: uuid.UUID
    scan_id: uuid.UUID
    format: ReportFormat
    audience: ReportAudience
    report_version: str
    size_bytes: int | None
    checksum_sha256: str | None
    generated_at: dt.datetime
