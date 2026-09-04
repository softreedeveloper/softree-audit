"""Esquemas de findings y del resultado SEO."""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import Any

from softree_audit.models.enums import (
    Confidence,
    FindingCategory,
    FindingSource,
    FindingStatus,
    Severity,
)
from softree_audit.schemas.common import ApiModel


class FindingRead(ApiModel):
    id: uuid.UUID
    scan_id: uuid.UUID
    source: FindingSource
    category: FindingCategory
    rule_id: str | None
    title: str
    severity: Severity
    confidence: Confidence
    url: str | None
    parameter: str | None
    evidence: str | None
    description: str
    impact: str | None
    remediation: str | None
    client_explanation: str | None
    cwe: str | None
    owasp: str | None
    references: list[Any]
    occurrences: int
    status: FindingStatus
    created_at: dt.datetime
    updated_at: dt.datetime


class FindingStatusUpdate(ApiModel):
    status: FindingStatus


class SeverityCounts(ApiModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0

    @property
    def total(self) -> int:
        return self.critical + self.high + self.medium + self.low + self.info


class SeoResultRead(ApiModel):
    scan_id: uuid.UUID
    pages_crawled: int
    urls_discovered: int
    missing_title: int
    duplicate_title: int
    missing_description: int
    duplicate_description: int
    missing_h1: int
    multiple_h1: int
    images_missing_alt: int
    broken_internal_links: int
    broken_external_links: int
    missing_canonical: int
    noindex_pages: int
    redirect_chains: int
    robots_txt_found: bool
    sitemap_found: bool
    sitemap_urls: int
    structured_data_summary: dict[str, Any]
    created_at: dt.datetime


class SiteSeoSummary(ApiModel):
    """Último resultado SEO de un sitio (`GET /sites/{id}/seo`)."""

    scan_id: uuid.UUID
    scan_status: str
    finished_at: dt.datetime | None
    result: SeoResultRead | None
    findings_by_severity: SeverityCounts
    top_rules: list[dict[str, Any]]


class SiteSecuritySummary(ApiModel):
    """Último resultado de seguridad de un sitio (`GET /sites/{id}/security`)."""

    scan_id: uuid.UUID
    scan_status: str
    finished_at: dt.datetime | None
    module_status: str
    module_detail: dict[str, Any] | None
    findings_by_severity: SeverityCounts
    top_findings: list[dict[str, Any]]


class PerformanceResultRead(ApiModel):
    url: str
    strategy: str
    performance_score: int | None
    accessibility_score: int | None
    best_practices_score: int | None
    seo_score: int | None
    lcp_ms: int | None
    cls: decimal.Decimal | None
    inp_ms: int | None
    fcp_ms: int | None
    tbt_ms: int | None
    speed_index_ms: int | None
    lighthouse_version: str | None
    has_field_data: bool
    created_at: dt.datetime


class GoogleScoreRead(ApiModel):
    category: str
    value: decimal.Decimal | None
    detail: dict[str, Any]


class SitePerformanceSummary(ApiModel):
    """Último resultado de rendimiento de un sitio (`GET /sites/{id}/performance`)."""

    scan_id: uuid.UUID
    scan_status: str
    finished_at: dt.datetime | None
    module_status: str
    module_detail: dict[str, Any] | None
    results: list[PerformanceResultRead]
    google_scores: list[GoogleScoreRead]
    findings_by_severity: SeverityCounts


class ScoreRead(ApiModel):
    system: str
    category: str
    value: decimal.Decimal | None
    weight: decimal.Decimal | None
    detail: dict[str, Any]
    engine_version: str


class ScanScoresResponse(ApiModel):
    """Los dos sistemas de puntuación, separados y etiquetados (§27)."""

    scan_id: uuid.UUID
    softree: list[ScoreRead]
    google: list[ScoreRead]
    softree_overall: decimal.Decimal | None
    band: str | None
    findings_by_severity: SeverityCounts
    disclaimer: str = (
        "El Softree Score es un indicador propio de Softree y no constituye una "
        "calificación oficial de Google."
    )
