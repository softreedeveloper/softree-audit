"""Servicio de autenticación: login, refresh, logout.

Decisiones en ADR-008. Reglas de seguridad en `docs/spec/security.md` §4.
"""

from __future__ import annotations

import datetime as dt
import uuid

import sqlalchemy as sa
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from softree_audit.core.config import Settings
from softree_audit.core.errors import (
    InactiveUserError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from softree_audit.core.logging import get_logger
from softree_audit.core.security import (
    IssuedToken,
    create_token,
    decode_token,
    hash_password,
    needs_rehash,
    utcnow,
    verify_password,
    waste_time_like_verification,
)
from softree_audit.models import RefreshToken, User

logger = get_logger(__name__)

# Ventana en la que un refresh token ya rotado puede volver a presentarse sin
# considerarse robado. Cubre la carrera legítima de dos pestañas abiertas o de
# una recarga mientras la renovación viajaba: cerrar la sesión en ese caso sería
# hostil y no aporta seguridad. Un reuso real llega mucho más tarde, cuando el
# cliente legítimo ya rotó varias veces.
REFRESH_REPLAY_GRACE = dt.timedelta(seconds=15)


class SessionPair:
    """Par de tokens emitido tras un login o un refresh."""

    __slots__ = ("access", "refresh")

    def __init__(self, access: IssuedToken, refresh: IssuedToken) -> None:
        self.access = access
        self.refresh = refresh


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    # ── Consultas ──────────────────────────────────────────────────────────

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            sa.select(User).where(User.email == email.strip().lower())
        )
        return result.scalar_one_or_none()

    async def get_active_user(self, user_id: uuid.UUID) -> User:
        result = await self._session.execute(sa.select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise InvalidTokenError()
        if not user.is_active:
            raise InactiveUserError()
        return user

    # ── Login ──────────────────────────────────────────────────────────────

    async def authenticate(self, email: str, password: str) -> User:
        """Valida credenciales sin permitir enumeración de usuarios."""
        user = await self.get_user_by_email(email)

        if user is None:
            # Consume un tiempo equivalente a una verificación real para que
            # «usuario inexistente» y «contraseña incorrecta» no se distingan.
            waste_time_like_verification()
            logger.info("auth.login_failed", reason="unknown_email")
            raise InvalidCredentialsError()

        if not verify_password(password, user.password_hash):
            logger.info("auth.login_failed", reason="bad_password", user_id=str(user.id))
            raise InvalidCredentialsError()

        if not user.is_active:
            logger.info("auth.login_failed", reason="inactive", user_id=str(user.id))
            raise InactiveUserError()

        # Si los parámetros de Argon2 cambiaron, se actualiza el hash al vuelo.
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        user.last_login_at = utcnow()
        logger.info("auth.login_succeeded", user_id=str(user.id))
        return user

    async def issue_session(
        self,
        user: User,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> SessionPair:
        access = self._create_access_token(user.id)
        refresh = self._create_refresh_token(user.id)

        self._session.add(
            RefreshToken(
                id=refresh.token_id,
                user_id=user.id,
                expires_at=refresh.expires_at,
                user_agent=(user_agent or None),
                ip_address=(ip_address or None),
            )
        )
        await self._session.flush()
        return SessionPair(access=access, refresh=refresh)

    # ── Refresh ────────────────────────────────────────────────────────────

    async def rotate_session(
        self,
        refresh_token: str,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> SessionPair:
        """Valida el refresh token, lo revoca y emite un par nuevo.

        El reuso de un token ya revocado o reemplazado invalida toda la sesión
        del usuario, porque indica que el token quedó expuesto.
        """
        claims = decode_token(
            refresh_token,
            secret_key=self._settings.secret_key,
            expected_type="refresh",
        )

        stored = await self._session.get(RefreshToken, claims.token_id)
        if stored is None:
            logger.warning("auth.refresh_unknown_jti", user_id=str(claims.subject))
            raise InvalidTokenError()

        if stored.is_revoked or stored.replaced_by_id is not None:
            replay = await self._replay_within_grace(stored)
            if replay is not None:
                return replay

            logger.warning("auth.refresh_reuse_detected", user_id=str(stored.user_id))
            await self.revoke_all_for_user(stored.user_id)
            # La revocación se confirma aquí: la petición terminará en 401 y el
            # rollback de la sesión desharía la medida de seguridad.
            await self._session.commit()
            raise InvalidTokenError()

        if stored.expires_at <= utcnow():
            raise InvalidTokenError()

        user = await self.get_active_user(stored.user_id)

        new_pair = await self.issue_session(user, user_agent=user_agent, ip_address=ip_address)
        stored.revoked_at = utcnow()
        stored.replaced_by_id = new_pair.refresh.token_id
        await self._session.flush()

        logger.info("auth.refresh_succeeded", user_id=str(user.id))
        return new_pair

    async def _replay_within_grace(self, stored: RefreshToken) -> SessionPair | None:
        """Repetición benigna de un token recién rotado.

        Devuelve un par nuevo si el token se rotó hace muy poco y su sucesor
        sigue vigente. Fuera de esa ventana, o si la cadena ya fue revocada, no
        se aplica y el reuso se trata como robo.
        """
        if stored.replaced_by_id is None or stored.revoked_at is None:
            return None
        if utcnow() - stored.revoked_at > REFRESH_REPLAY_GRACE:
            return None

        successor = await self._session.get(RefreshToken, stored.replaced_by_id)
        if successor is None or successor.is_revoked or successor.expires_at <= utcnow():
            return None

        user = await self.get_active_user(stored.user_id)
        pair = await self.issue_session(
            user, user_agent=successor.user_agent, ip_address=successor.ip_address
        )
        successor.revoked_at = utcnow()
        successor.replaced_by_id = pair.refresh.token_id
        await self._session.flush()

        logger.info(
            "auth.refresh_replayed_within_grace",
            user_id=str(stored.user_id),
            grace_seconds=int(REFRESH_REPLAY_GRACE.total_seconds()),
        )
        return pair

    # ── Logout y revocación ────────────────────────────────────────────────

    async def logout(self, refresh_token: str | None) -> None:
        """Revoca el refresh token actual. Idempotente."""
        if not refresh_token:
            return
        try:
            claims = decode_token(
                refresh_token,
                secret_key=self._settings.secret_key,
                expected_type="refresh",
            )
        except InvalidTokenError:
            # Un token ilegible ya no sirve para nada; no es un error de logout.
            return

        stored = await self._session.get(RefreshToken, claims.token_id)
        if stored is not None and not stored.is_revoked:
            stored.revoked_at = utcnow()
            await self._session.flush()
            logger.info("auth.logout", user_id=str(stored.user_id))

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        await self._session.execute(
            sa.update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await self._session.flush()
        logger.warning("auth.all_sessions_revoked", user_id=str(user_id))

    async def purge_expired_tokens(self, *, older_than: dt.datetime | None = None) -> int:
        """Elimina registros de refresh tokens ya expirados."""
        cutoff = older_than or utcnow()
        result = await self._session.execute(
            sa.delete(RefreshToken).where(RefreshToken.expires_at < cutoff)
        )
        deleted: int = result.rowcount if isinstance(result, CursorResult) else 0
        return max(deleted, 0)

    # ── Internos ───────────────────────────────────────────────────────────

    def _create_access_token(self, user_id: uuid.UUID) -> IssuedToken:
        return create_token(
            subject=user_id,
            token_type="access",  # noqa: S106 - tipo de token, no una credencial
            secret_key=self._settings.secret_key,
            ttl=dt.timedelta(minutes=self._settings.access_token_ttl_minutes),
        )

    def _create_refresh_token(self, user_id: uuid.UUID) -> IssuedToken:
        return create_token(
            subject=user_id,
            token_type="refresh",  # noqa: S106 - tipo de token, no una credencial
            secret_key=self._settings.secret_key,
            ttl=dt.timedelta(days=self._settings.refresh_token_ttl_days),
        )
