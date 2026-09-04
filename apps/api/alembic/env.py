"""Entorno de Alembic, con motor asíncrono."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

# Importar el paquete de modelos registra todas las tablas en Base.metadata.
import softree_audit.models  # noqa: F401
import sqlalchemy as sa
from alembic import context
from softree_audit.core.config import get_settings
from softree_audit.db.base import Base
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def _enum_check_constraint_names() -> set[str]:
    """Nombres de los CHECK que genera `sa.Enum(native_enum=False)`.

    SQLAlchemy los marca como «type bound», y el autogenerado de Alembic los
    excluye del lado de los modelos pero sí los refleja del lado de la base de
    datos. Sin este filtro, `alembic check` los reportaría como eliminados en
    cada ejecución. Los nombres son deterministas por la convención
    `ck_%(table_name)s_%(constraint_name)s` de `db/base.py`.
    """
    names: set[str] = set()
    for table in target_metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, sa.Enum) and not column.type.native_enum:
                names.add(f"ck_{table.name}_{column.type.name}")
    return names


ENUM_CHECK_CONSTRAINTS = _enum_check_constraint_names()


def include_object(
    _object: object,
    name: str | None,
    type_: str,
    _reflected: bool,
    _compare_to: object,
) -> bool:
    return not (type_ == "check_constraint" and name in ENUM_CHECK_CONSTRAINTS)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=None,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
