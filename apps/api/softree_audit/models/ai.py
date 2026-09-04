"""Análisis asistido por IA de una auditoría.

Se persiste para que el reporte sea reproducible: dos descargas del mismo scan
entregan el mismo texto, y queda registrado qué modelo lo escribió y con qué
versión del prompt (`docs/spec/reports.md` §8).
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

if TYPE_CHECKING:
    from softree_audit.models.scan import Scan


class AiAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_analyses"
    # Un análisis por auditoría: regenerarlo sustituye el anterior.
    __table_args__ = (sa.UniqueConstraint("scan_id"),)

    scan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )

    model: Mapped[str] = mapped_column(sa.Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(sa.Text, nullable=False)

    summary: Mapped[str] = mapped_column(sa.Text, nullable=False)
    recommendations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )
    risks: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
    )

    # Trazabilidad de la llamada, para poder auditar coste y latencia.
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    tokens_prompt: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    tokens_completion: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    generated_at: Mapped[dt.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    scan: Mapped[Scan] = relationship(back_populates="ai_analysis")
