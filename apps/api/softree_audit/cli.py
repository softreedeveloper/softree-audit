"""Interfaz de línea de comandos administrativa.

No existe registro público: los usuarios se crean desde aquí (D-003).
"""

from __future__ import annotations

import asyncio
import datetime as dt

import sqlalchemy as sa
import typer
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from softree_audit.core.config import get_settings
from softree_audit.core.crypto import DecryptionError, SecretBox
from softree_audit.core.logging import configure_logging
from softree_audit.core.security import hash_password
from softree_audit.db.session import create_engine, create_session_factory
from softree_audit.models import ConnectionStatus, RefreshToken, SearchConsoleConnection, User
from softree_audit.schemas.auth import PasswordReset, UserCreate
from softree_audit.version import APP_VERSION, REPORT_VERSION, SCAN_ENGINE_VERSION

app = typer.Typer(help="Utilidades administrativas de Softree Audit", no_args_is_help=True)


@app.command("version")
def version() -> None:
    """Muestra las versiones del producto, del motor y del reporte."""
    typer.echo(f"Softree Audit {APP_VERSION}")
    typer.echo(f"Scan Engine {SCAN_ENGINE_VERSION}")
    typer.echo(f"Report {REPORT_VERSION}")


@app.command("create-user")
def create_user(
    email: str = typer.Option(..., prompt="Email"),
    full_name: str = typer.Option(..., prompt="Nombre completo"),
    password: str = typer.Option(
        ..., prompt="Contraseña", hide_input=True, confirmation_prompt=True
    ),
) -> None:
    """Crea un usuario interno."""
    try:
        payload = UserCreate(email=email, full_name=full_name, password=password)
    except ValidationError as exc:
        for error in exc.errors():
            field = ".".join(str(part) for part in error["loc"])
            typer.echo(f"  {field}: {error['msg']}", err=True)
        raise typer.Exit(code=1) from exc

    asyncio.run(_create_user(payload))


async def _create_user(payload: UserCreate) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    engine = create_engine(settings)
    factory = create_session_factory(engine)

    try:
        async with factory() as session:
            existing = await session.execute(sa.select(User).where(User.email == payload.email))
            if existing.scalar_one_or_none() is not None:
                typer.echo(f"Ya existe un usuario con el email {payload.email}.", err=True)
                raise typer.Exit(code=1)

            user = User(
                email=payload.email,
                full_name=payload.full_name,
                password_hash=hash_password(payload.password),
            )
            session.add(user)
            await session.commit()
            typer.echo(f"Usuario creado: {user.email} ({user.id})")
    finally:
        await engine.dispose()


@app.command("reset-password")
def reset_password(
    email: str = typer.Option(..., prompt="Email"),
    password: str = typer.Option(
        ..., prompt="Contraseña nueva", hide_input=True, confirmation_prompt=True
    ),
) -> None:
    """Cambia la contraseña de un usuario existente.

    Revoca además sus sesiones abiertas: si la contraseña se cambia, un refresh
    token emitido con la anterior no debe seguir sirviendo.
    """
    try:
        payload = PasswordReset(email=email, password=password)
    except ValidationError as exc:
        for error in exc.errors():
            field = ".".join(str(part) for part in error["loc"])
            typer.echo(f"  {field}: {error['msg']}", err=True)
        raise typer.Exit(code=1) from exc

    asyncio.run(_reset_password(payload))


async def _reset_password(payload: PasswordReset) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    engine = create_engine(settings)
    factory = create_session_factory(engine)

    try:
        async with factory() as session:
            try:
                revoked = await apply_password_reset(session, payload)
            except UserNotFoundError:
                typer.echo(f"No existe ningún usuario con el email {payload.email}.", err=True)
                raise typer.Exit(code=1) from None

            typer.echo(f"Contraseña actualizada: {payload.email}")
            typer.echo(f"Sesiones revocadas: {revoked}")
    finally:
        await engine.dispose()


class UserNotFoundError(Exception):
    """El email no corresponde a ningún usuario."""


async def apply_password_reset(session: AsyncSession, payload: PasswordReset) -> int:
    """Cambia la contraseña y revoca las sesiones abiertas.

    Devuelve cuántas sesiones se revocaron. Separado del comando para poder
    probarlo contra la base de datos de pruebas.
    """
    user = await session.scalar(sa.select(User).where(User.email == payload.email))
    if user is None:
        raise UserNotFoundError(payload.email)

    user.password_hash = hash_password(payload.password)
    revoked = await session.scalar(
        sa.select(sa.func.count())
        .select_from(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
    )
    await session.execute(
        sa.update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=dt.datetime.now(dt.UTC))
    )
    await session.commit()
    return int(revoked or 0)


@app.command("rotate-secrets")
def rotate_secrets() -> None:
    """Recifra las credenciales de terceros con la SECRET_KEY actual.

    Requiere `SECRET_KEY_PREVIOUS` con la clave anterior. Procedimiento completo
    en `docs/development/deployment.md`.
    """
    settings = get_settings()
    if not settings.secret_key_previous:
        typer.echo(
            "SECRET_KEY_PREVIOUS no está definida: nada que rotar.",
            err=True,
        )
        raise typer.Exit(code=1)
    asyncio.run(_rotate_secrets())


async def _rotate_secrets() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    box = SecretBox(settings.secret_key, settings.secret_key_previous)
    engine = create_engine(settings)
    factory = create_session_factory(engine)

    rotated = 0
    failed = 0
    try:
        async with factory() as session:
            result = await session.execute(sa.select(SearchConsoleConnection))
            for connection in result.scalars():
                try:
                    connection.refresh_token_encrypted = box.rotate(
                        connection.refresh_token_encrypted
                    )
                    rotated += 1
                except DecryptionError:
                    # La conexión queda marcada para reconexión manual; nunca se
                    # registra el contenido del token.
                    connection.status = ConnectionStatus.ERROR
                    connection.last_error = "No fue posible recifrar la credencial almacenada."
                    failed += 1
            await session.commit()
    finally:
        await engine.dispose()

    typer.echo(f"Credenciales recifradas: {rotated}")
    if failed:
        typer.echo(f"Credenciales que requieren reconexión: {failed}", err=True)


if __name__ == "__main__":  # pragma: no cover
    app()
