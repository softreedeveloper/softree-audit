"""Conexión con Google Search Console y métricas sincronizadas.

Los datos pertenecen a la propiedad autorizada. Una conexión está ligada a un
único proyecto y no se comparte entre proyectos (§53, ADR-005).
"""

from __future__ import annotations

import datetime as dt
import decimal
import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from softree_audit.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from softree_audit.models.enums import (
    ConnectionStatus,
    SearchConsoleDimension,
    SearchConsolePeriod,
    enum_column,
)

if TYPE_CHECKING:
    from softree_audit.models.project import Project
    from softree_audit.models.scan import Scan


class SearchConsoleConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "search_console_connections"

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    google_account_email: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    property_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    # Solo se persiste el refresh token, cifrado (security.md §7).
    # El access token se obtiene en memoria en cada uso.
    refresh_token_encrypted: Mapped[bytes] = mapped_column(sa.LargeBinary, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(sa.Text), nullable=False)

    status: Mapped[ConnectionStatus] = mapped_column(
        enum_column(ConnectionStatus, "connection_status"),
        nullable=False,
        server_default=ConnectionStatus.CONNECTED.value,
    )
    last_sync_at: Mapped[dt.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    project: Mapped[Project] = relationship(back_populates="search_console_connection")


class SearchConsoleMetric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "search_console_metrics"
    __table_args__ = (
        sa.UniqueConstraint("scan_id", "period", "dimension", "dimension_value"),
        sa.Index("ix_search_console_metrics_scan_period_dim", "scan_id", "period", "dimension"),
    )

    scan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    period: Mapped[SearchConsolePeriod] = mapped_column(
        enum_column(SearchConsolePeriod, "search_console_period"), nullable=False
    )
    dimension: Mapped[SearchConsoleDimension] = mapped_column(
        enum_column(SearchConsoleDimension, "search_console_dimension"), nullable=False
    )
    dimension_value: Mapped[str] = mapped_column(sa.Text, nullable=False)

    clicks: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    impressions: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    ctr: Mapped[decimal.Decimal] = mapped_column(sa.Numeric(7, 6), nullable=False)
    position: Mapped[decimal.Decimal] = mapped_column(sa.Numeric(6, 2), nullable=False)

    scan: Mapped[Scan] = relationship(back_populates="search_console_metrics")
