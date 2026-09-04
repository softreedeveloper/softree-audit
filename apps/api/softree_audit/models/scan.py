"""Scan y estado por módulo.

Cada módulo del pipeline tiene su propio estado, de modo que la falla de una
integración externa no cancela el scan completo (§13, §14).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from softree_audit.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from softree_audit.models.enums import (
    ModuleName,
    ModuleStatus,
    ScanStatus,
    ScanType,
    enum_column,
)

if TYPE_CHECKING:
    from softree_audit.models.ai import AiAnalysis
    from softree_audit.models.finding import Finding
    from softree_audit.models.page import Page
    from softree_audit.models.report import Report
    from softree_audit.models.results import PerformanceResult, SEOResult
    from softree_audit.models.score import Score
    from softree_audit.models.search_console import SearchConsoleMetric
    from softree_audit.models.site import Site


class Scan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scans"
    __table_args__ = (
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="progress_range"),
        sa.Index("ix_scans_site_id_queued_at", "site_id", "queued_at"),
    )

    site_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    scan_type: Mapped[ScanType] = mapped_column(enum_column(ScanType, "scan_type"), nullable=False)
    status: Mapped[ScanStatus] = mapped_column(
        enum_column(ScanStatus, "scan_status"), nullable=False, index=True
    )
    progress: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False, server_default="0")

    queued_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    # Scope efectivo en el momento del scan: hace reproducible un scan histórico
    # aunque el scope del sitio cambie después (database.md §scans).
    scope_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    engine_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    app_version: Mapped[str] = mapped_column(sa.Text, nullable=False)

    site: Mapped[Site] = relationship(back_populates="scans")
    modules: Mapped[list[ScanModuleRun]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ScanModuleRun.created_at",
    )
    pages: Mapped[list[Page]] = relationship(
        back_populates="scan", cascade="all, delete-orphan", passive_deletes=True
    )
    findings: Mapped[list[Finding]] = relationship(
        back_populates="scan", cascade="all, delete-orphan", passive_deletes=True
    )
    seo_result: Mapped[SEOResult | None] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    performance_results: Mapped[list[PerformanceResult]] = relationship(
        back_populates="scan", cascade="all, delete-orphan", passive_deletes=True
    )
    search_console_metrics: Mapped[list[SearchConsoleMetric]] = relationship(
        back_populates="scan", cascade="all, delete-orphan", passive_deletes=True
    )
    scores: Mapped[list[Score]] = relationship(
        back_populates="scan", cascade="all, delete-orphan", passive_deletes=True
    )
    reports: Mapped[list[Report]] = relationship(
        back_populates="scan", cascade="all, delete-orphan", passive_deletes=True
    )
    ai_analysis: Mapped[AiAnalysis | None] = relationship(
        back_populates="scan", cascade="all, delete-orphan", passive_deletes=True
    )


class ScanModuleRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Ejecución de un módulo dentro de un scan."""

    __tablename__ = "scan_modules"
    __table_args__ = (sa.UniqueConstraint("scan_id", "module"),)

    scan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    module: Mapped[ModuleName] = mapped_column(
        enum_column(ModuleName, "module_name"), nullable=False
    )
    status: Mapped[ModuleStatus] = mapped_column(
        enum_column(ModuleStatus, "module_status"), nullable=False
    )
    started_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    scan: Mapped[Scan] = relationship(back_populates="modules")
