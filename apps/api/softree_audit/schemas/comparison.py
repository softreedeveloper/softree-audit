"""Esquemas de comparación e histórico."""

from __future__ import annotations

import datetime as dt
import uuid

from softree_audit.schemas.common import ApiModel


class ScanRef(ApiModel):
    scan_id: uuid.UUID
    status: str
    finished_at: dt.datetime | None
    engine_version: str


class FindingChangeRead(ApiModel):
    kind: str
    fingerprint: str
    rule_id: str | None
    title: str
    severity: str
    category: str
    url: str | None
    previous_severity: str | None
    occurrences: int
    previous_occurrences: int | None


class MetricDeltaRead(ApiModel):
    key: str
    label: str
    previous: float | None
    current: float | None
    delta: float | None
    direction: str
    unit: str
    higher_is_better: bool


class ComparisonResponse(ApiModel):
    current: ScanRef
    previous: ScanRef
    counts: dict[str, int]
    changes: list[FindingChangeRead]
    metrics: list[MetricDeltaRead]
    compared_sources: list[str]
    sources_only_in_current: list[str]
    sources_only_in_previous: list[str]


class HistoryEntry(ApiModel):
    scan_id: uuid.UUID
    scan_type: str
    status: str
    queued_at: dt.datetime
    finished_at: dt.datetime | None
    duration_ms: int | None
    engine_version: str
    softree_overall: float | None
    open_findings: int


class RecentScan(ApiModel):
    scan_id: uuid.UUID
    site_name: str
    site_base_url: str
    status: str
    scan_type: str
    queued_at: dt.datetime
    finished_at: dt.datetime | None


class DashboardResponse(ApiModel):
    projects: int
    sites: int
    authorized_sites: int
    scans: int
    scans_in_progress: int
    average_score: float | None
    scored_sites: int
    open_findings_by_severity: dict[str, int]
    recent_scans: list[RecentScan]
