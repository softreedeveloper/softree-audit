"""Infraestructura de las pruebas de integración.

Requieren PostgreSQL y Redis reales. Si `TEST_DATABASE_URL` no está definida,
las pruebas se omiten con un motivo explícito en lugar de fingir éxito
(`docs/development/testing.md`).

El esquema se crea aplicando las migraciones de Alembic en un subproceso, de
modo que cada ejecución también verifica que las migraciones son aplicables.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from unittest import mock

import pytest
import pytest_asyncio
import softree_audit
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from softree_audit.core.config import Settings
from softree_audit.core.security import hash_password
from softree_audit.db.session import create_engine, create_session_factory
from softree_audit.main import create_app
from softree_audit.models import User
from sqlalchemy.ext.asyncio import AsyncSession

API_ROOT = pathlib.Path(softree_audit.__file__).parent.parent

TEST_PASSWORD = "contrasena-de-prueba-larga"
TEST_EMAIL = "qa@softree.test"


# Tablas que se vacían entre pruebas. `users` incluida: cada prueba crea su
# propio usuario.
class FakeQueue:
    """Doble de la cola de arq.

    Las pruebas de integración verifican la API, no el worker: encolar de verdad
    exigiría un proceso aparte y haría las pruebas lentas y no deterministas.
    """

    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[object, ...]]] = []

    async def enqueue_job(self, function: str, *args: object, **kwargs: object) -> None:
        self.jobs.append((function, args))

    async def aclose(self) -> None:
        return None


TRUNCATED_TABLES = (
    "refresh_tokens",
    "reports",
    "scores",
    "search_console_metrics",
    "search_console_connections",
    "performance_results",
    "seo_results",
    "findings",
    "pages",
    "scan_modules",
    "scans",
    "scopes",
    "sites",
    "projects",
    "users",
)


def _database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL no está definida: se omiten las pruebas de integración. "
            "Ver docs/development/testing.md"
        )
    return url


@pytest.fixture(scope="session")
def settings() -> Settings:
    url = _database_url()
    redis_url = os.environ.get("TEST_REDIS_URL", "redis://redis:6379/15")

    # El entorno del contenedor se vacía mientras se construye la configuración.
    # No basta con `_env_file=None`: pydantic-settings sigue leyendo las
    # variables del proceso, y entonces una credencial presente en el `.env` del
    # desarrollador cambiaría el resultado de las pruebas. Ocurrió con
    # GOOGLE_CLIENT_ID: al configurarla, una prueba que esperaba «integración no
    # configurada» empezó a ver la integración configurada.
    with mock.patch.dict(os.environ, {}, clear=True):
        return _build_settings(url, redis_url)


def _build_settings(url: str, redis_url: str) -> Settings:
    return Settings(
        # Aislado del .env local: la configuración de la prueba es explícita.
        _env_file=None,
        app_env="development",
        secret_key="clave-de-integracion-suficientemente-larga-0123",
        database_url=url,
        redis_url=redis_url,
        log_format="console",
        # Explícito: la protección de red debe estar activa en las pruebas,
        # independientemente del .env de desarrollo.
        ssrf_allow_private_networks=False,
    )


@pytest.fixture(scope="session", autouse=True)
def _schema(settings: Settings) -> Iterator[None]:
    """Aplica `alembic upgrade head` y lo revierte al terminar."""
    env = {**os.environ, "DATABASE_URL": settings.database_url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    yield
    subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=API_ROOT,
        env=env,
        check=False,
        capture_output=True,
    )


@pytest_asyncio.fixture
async def app_context(settings: Settings) -> AsyncIterator[tuple[object, AsyncSession]]:
    """Aplicación con sus recursos inicializados.

    El ciclo de vida (`lifespan`) no se ejecuta: los recursos se inyectan
    directamente para poder compartir la sesión con la prueba.
    """
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async with engine.begin() as connection:
        await connection.execute(
            sa.text(f"TRUNCATE {', '.join(TRUNCATED_TABLES)} RESTART IDENTITY CASCADE")
        )
    await redis.flushdb()

    app = create_app(settings)
    app.state.engine = engine
    app.state.session_factory = factory
    app.state.redis = redis
    app.state.queue = FakeQueue()

    async with factory() as session:
        yield app, session

    await redis.aclose()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(app_context: tuple[object, AsyncSession]) -> AsyncIterator[AsyncClient]:
    app, _ = app_context
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
    ) as http_client:
        yield http_client


@pytest_asyncio.fixture
async def user(app_context: tuple[object, AsyncSession]) -> User:
    _, session = app_context
    record = User(
        email=TEST_EMAIL,
        full_name="QA Softree",
        password_hash=hash_password(TEST_PASSWORD),
    )
    session.add(record)
    await session.commit()
    return record


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, user: User) -> AsyncClient:
    """Cliente con el `Authorization: Bearer` de un usuario ya autenticado."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
    return client


@pytest_asyncio.fixture
async def other_user(app_context: tuple[object, AsyncSession]) -> User:
    """Segundo usuario, para verificar el aislamiento entre cuentas."""
    _, session = app_context
    record = User(
        email="otro@softree.test",
        full_name="Otro usuario",
        password_hash=hash_password(TEST_PASSWORD),
    )
    session.add(record)
    await session.commit()
    return record
