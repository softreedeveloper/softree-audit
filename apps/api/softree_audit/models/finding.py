"""Finding unificado.

Todas las fuentes (ZAP, SEO, crawler, PageSpeed, Search Console) convergen en
este modelo tras pasar por el normalizador (§18, §24). La deduplicación se
apoya en el índice único `(scan_id, fingerprint)` (§25).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from softree_audit.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from softree_audit.models.enums import (
    Confidence,
    FindingCategory,
    FindingSource,
    FindingStatus,
    Severity,
    enum_column,
)

if TYPE_CHECKING:
    from softree_audit.models.scan import Scan


class Finding(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "findings"
    __table_args__ = (
        sa.UniqueConstraint("scan_id", "fingerprint"),
        sa.Index("ix_findings_scan_id_severity", "scan_id", "severity"),
        sa.Index("ix_findings_scan_id_source", "scan_id", "source"),
        # Permite arrastrar el estado `accepted` o `false_positive` entre scans
        # del mismo sitio.
        sa.Index("ix_findings_fingerprint", "fingerprint"),
        sa.CheckConstraint("occurrences >= 1", name="occurrences_positive"),
    )

    scan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )

    source: Mapped[FindingSource] = mapped_column(
        enum_column(FindingSource, "finding_source"), nullable=False
    )
    category: Mapped[FindingCategory] = mapped_column(
        enum_column(FindingCategory, "finding_category"), nullable=False
    )
    rule_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    title: Mapped[str] = mapped_column(sa.Text, nullable=False)
    severity: Mapped[Severity] = mapped_column(
        enum_column(Severity, "finding_severity"), nullable=False
    )
    confidence: Mapped[Confidence] = mapped_column(
        enum_column(Confidence, "finding_confidence"), nullable=False
    )

    url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    parameter: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    evidence: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    description: Mapped[str] = mapped_column(sa.Text, nullable=False)
    impact: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    remediation: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # Redacción no técnica para el resumen ejecutivo del reporte (§34).
    client_explanation: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    cwe: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    owasp: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    references: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )

    occurrences: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    fingerprint: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[FindingStatus] = mapped_column(
        enum_column(FindingStatus, "finding_status"),
        nullable=False,
        server_default=FindingStatus.OPEN.value,
    )

    # Payload original de la fuente, solo para trazabilidad y reproceso.
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    scan: Mapped[Scan] = relationship(back_populates="findings")
