"""Página rastreada por el crawler."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from softree_audit.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from softree_audit.models.scan import Scan


class Page(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pages"
    __table_args__ = (
        # Se indexa por hash porque una URL puede exceder el tamaño máximo de
        # una entrada de índice B-tree (database.md §pages).
        sa.UniqueConstraint("scan_id", "url_hash"),
        sa.Index("ix_pages_scan_id_status_code", "scan_id", "status_code"),
    )

    scan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    url_hash: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    depth: Mapped[int] = mapped_column(sa.SmallInteger, nullable=False)
    # URL desde la que se descubrió la página. La regla SEO-008 («enlace
    # interno roto») necesita saber quién enlaza al recurso que falla.
    discovered_from: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    status_code: Mapped[int | None] = mapped_column(sa.SmallInteger, nullable=True)
    content_type: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    content_length: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    title: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    meta_description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    canonical: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    meta_robots: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    h1: Mapped[list[str]] = mapped_column(ARRAY(sa.Text), nullable=False, server_default="{}")
    h2: Mapped[list[str]] = mapped_column(ARRAY(sa.Text), nullable=False, server_default="{}")

    internal_links: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    external_links: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    images_total: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    images_missing_alt: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    scripts_total: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    forms_total: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")

    redirect_chain: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    # JSON-LD, Schema.org, OpenGraph y Twitter Cards (§20).
    structured_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )

    is_indexable: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    scan: Mapped[Scan] = relationship(back_populates="pages")
