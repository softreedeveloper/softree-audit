"""Reporte generado."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from softree_audit.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from softree_audit.models.enums import ReportAudience, ReportFormat, enum_column

if TYPE_CHECKING:
    from softree_audit.models.scan import Scan


class Report(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (sa.UniqueConstraint("scan_id", "format", "audience", "report_version"),)

    scan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    format: Mapped[ReportFormat] = mapped_column(
        enum_column(ReportFormat, "report_format"), nullable=False
    )
    report_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    audience: Mapped[ReportAudience] = mapped_column(
        enum_column(ReportAudience, "report_audience"),
        nullable=False,
        server_default=ReportAudience.COMBINED.value,
    )

    storage_path: Mapped[str] = mapped_column(sa.Text, nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    generated_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    scan: Mapped[Scan] = relationship(back_populates="reports")
