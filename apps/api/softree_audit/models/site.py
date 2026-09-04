"""Sitio auditado y su scope.

Un sitio solo es escaneable con autorización registrada
(`docs/spec/security.md` §1).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from softree_audit.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from softree_audit.models.project import Project
    from softree_audit.models.scan import Scan

# Límites máximos del scope. El usuario puede bajarlos, nunca superarlos.
MAX_PAGES_LIMIT = 5000
MAX_DEPTH_LIMIT = 10
MAX_TIMEOUT_SECONDS = 120
MAX_REQUEST_DELAY_MS = 10_000
MAX_CONCURRENCY = 16


class Site(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sites"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "base_url"),
        sa.CheckConstraint("base_url ~* '^https?://'", name="base_url_scheme"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    base_url: Mapped[str] = mapped_column(sa.Text, nullable=False)

    authorized_by: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    authorization_date: Mapped[dt.date | None] = mapped_column(sa.Date, nullable=True)
    authorization_notes: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())

    project: Mapped[Project] = relationship(back_populates="sites")
    scope: Mapped[Scope | None] = relationship(
        back_populates="site",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    scans: Mapped[list[Scan]] = relationship(
        back_populates="site", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def is_authorized(self) -> bool:
        """Un sitio sin autorización registrada no puede escanearse."""
        return bool(self.authorized_by) and self.authorization_date is not None


class Scope(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scopes"
    __table_args__ = (
        sa.CheckConstraint(f"max_pages BETWEEN 1 AND {MAX_PAGES_LIMIT}", name="max_pages_range"),
        sa.CheckConstraint(f"max_depth BETWEEN 1 AND {MAX_DEPTH_LIMIT}", name="max_depth_range"),
        sa.CheckConstraint(
            f"timeout_seconds BETWEEN 1 AND {MAX_TIMEOUT_SECONDS}", name="timeout_range"
        ),
        sa.CheckConstraint(
            f"request_delay_ms BETWEEN 0 AND {MAX_REQUEST_DELAY_MS}", name="delay_range"
        ),
        sa.CheckConstraint(
            f"concurrency BETWEEN 1 AND {MAX_CONCURRENCY}", name="concurrency_range"
        ),
        sa.CheckConstraint("cardinality(allowed_domains) > 0", name="allowed_domains_present"),
    )

    site_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    allowed_domains: Mapped[list[str]] = mapped_column(ARRAY(sa.Text), nullable=False)
    allowed_paths: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text), nullable=False, server_default="{}"
    )
    excluded_paths: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text), nullable=False, server_default="{}"
    )

    max_pages: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="200")
    max_depth: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="3")
    timeout_seconds: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="20")
    request_delay_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="200")
    concurrency: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="4")

    respect_robots: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    zap_spider_enabled: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    # Comprobar enlaces salientes exige peticiones a dominios de terceros, por
    # lo que es opcional y viene desactivado (SEO-009).
    check_external_links: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )

    # Reservado para scanning autenticado (architecture.md §11). Sin uso en el MVP.
    auth_profile_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)

    site: Mapped[Site] = relationship(back_populates="scope")
