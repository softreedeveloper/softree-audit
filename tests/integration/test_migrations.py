"""Coherencia entre las migraciones y los modelos."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest
import softree_audit
import sqlalchemy as sa
from softree_audit.core.config import Settings
from softree_audit.db.base import Base
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

API_ROOT = pathlib.Path(softree_audit.__file__).parent.parent


def test_migrations_match_the_models(settings: Settings) -> None:
    """`alembic check` falla si el modelo y la migración divergen.

    Evita el caso clásico de un campo añadido al modelo sin migración.
    """
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=API_ROOT,
        env={**os.environ, "DATABASE_URL": settings.database_url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_single_alembic_head() -> None:
    """Una sola cabeza: ramas de migración divergentes rompen el despliegue."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    heads = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1, result.stdout


async def test_every_model_table_exists(app_context: tuple[object, AsyncSession]) -> None:
    _, session = app_context
    result = await session.execute(
        sa.text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    )
    existing = {row[0] for row in result}
    expected = set(Base.metadata.tables)
    assert expected <= existing, expected - existing


async def test_every_table_has_timestamps(app_context: tuple[object, AsyncSession]) -> None:
    """Convención de `docs/spec/database.md`."""
    _, session = app_context
    result = await session.execute(
        sa.text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name IN ('created_at', 'updated_at')"
        )
    )
    by_table: dict[str, set[str]] = {}
    for table, column in result:
        by_table.setdefault(table, set()).add(column)

    for table in Base.metadata.tables:
        if table == "alembic_version":
            continue
        assert by_table.get(table) == {"created_at", "updated_at"}, table
