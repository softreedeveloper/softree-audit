"""Resultados agregados de SEO y de rendimiento."""

from __future__ import annotations

import decimal
import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from softree_audit.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from softree_audit.models.enums import PageSpeedStrategy, enum_column

if TYPE_CHECKING:
    from softree_audit.models.scan import Scan


class SEOResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Agregados SEO del scan. El detalle por página vive en `pages`."""

    __tablename__ = "seo_results"

    scan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    pages_crawled: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    urls_discovered: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")

    missing_title: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    duplicate_title: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    missing_description: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    duplicate_description: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    missing_h1: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    multiple_h1: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    images_missing_alt: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    broken_internal_links: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    broken_external_links: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    missing_canonical: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    noindex_pages: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    redirect_chains: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")

    robots_txt_found: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    sitemap_found: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    sitemap_urls: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")

    structured_data_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )

    scan: Mapped[Scan] = relationship(back_populates="seo_result")


class PerformanceResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Resultado de PageSpeed Insights para una URL y estrategia."""

    __tablename__ = "performance_results"
    __table_args__ = (
        sa.UniqueConstraint("scan_id", "url", "strategy"),
        sa.CheckConstraint(
            "performance_score IS NULL OR performance_score BETWEEN 0 AND 100",
            name="performance_score_range",
        ),
    )

    scan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    strategy: Mapped[PageSpeedStrategy] = mapped_column(
        enum_column(PageSpeedStrategy, "pagespeed_strategy"), nullable=False
    )

    performance_score: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True)
    accessibility_score: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True)
    best_practices_score: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True)
    seo_score: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True)

    lcp_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    cls: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(6, 4), nullable=True)
    # INP solo existe con datos de campo (CrUX). `null` significa «sin datos»,
    # nunca cero (R4).
    inp_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    fcp_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    tbt_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    speed_index_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    lighthouse_version: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    has_field_data: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )

    # Respuesta original completa, para trazabilidad (§21).
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    scan: Mapped[Scan] = relationship(back_populates="performance_results")
