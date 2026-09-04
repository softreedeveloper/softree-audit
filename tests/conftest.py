"""Configuración común de las pruebas."""

from __future__ import annotations

import os

import pytest

# Valores mínimos para que `Settings` sea instanciable en pruebas unitarias sin
# depender del entorno del desarrollador.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-0123456789")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://softree:softree@localhost:5432/softree_audit"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    """Evita que una prueba herede la configuración cacheada de otra."""
    from softree_audit.core.config import get_settings

    get_settings.cache_clear()
