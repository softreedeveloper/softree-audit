"""Scores persistidos.

`system` separa el score propio del de Google, para no presentar un cálculo
interno como calificación oficial (§27, ADR-006). El peso aplicado se guarda
junto al valor, de modo que un cambio de configuración no altere scans
históricos.
"""

from __future__ import annotations

import decimal
import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from softree_audit.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from softree_audit.models.enums import ScoreCategory, ScoreSystem, enum_column

if TYPE_CHECKING:
    from softree_audit.models.scan import Scan


class Score(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scores"
    __table_args__ = (
        sa.UniqueConstraint("scan_id", "system", "category"),
        sa.CheckConstraint("value IS NULL OR value BETWEEN 0 AND 100", name="value_range"),
        sa.CheckConstraint("weight IS NULL OR weight BETWEEN 0 AND 1", name="weight_range"),
    )

    scan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        sa.ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    system: Mapped[ScoreSystem] = mapped_column(
        enum_column(ScoreSystem, "score_system"), nullable=False
    )
    category: Mapped[ScoreCategory] = mapped_column(
        enum_column(ScoreCategory, "score_category"), nullable=False
    )

    value: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(5, 2), nullable=True)
    # Solo aplica al sistema `softree`.
    weight: Mapped[decimal.Decimal | None] = mapped_column(sa.Numeric(5, 4), nullable=True)

    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    engine_version: Mapped[str] = mapped_column(sa.Text, nullable=False)

    scan: Mapped[Scan] = relationship(back_populates="scores")
