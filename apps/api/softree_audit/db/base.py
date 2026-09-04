"""Base declarativa, tipos comunes y mixins.

Convenciones en `docs/spec/database.md`.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from uuid6 import uuid7

# Nomenclatura explícita para que Alembic genere nombres estables y reversibles.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # `created_at` y `updated_at` los calcula el servidor. Sin `eager_defaults`
    # SQLAlchemy los deja expirados tras un INSERT o UPDATE y los recargaría de
    # forma perezosa, lo que en un contexto asíncrono provoca `MissingGreenlet`
    # al serializar la respuesta. Con esta opción se recuperan con RETURNING en
    # la misma sentencia.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 - lo define DeclarativeBase

    def to_dict(self) -> dict[str, Any]:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}


def uuid_pk() -> Mapped[uuid.UUID]:
    """Clave primaria UUID v7 generada en la aplicación (ADR-002)."""
    return mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid7)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


def utc_now_server_default() -> Any:
    return text("now()")
