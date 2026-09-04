"""Servicio de conexión con Google Search Console.

Aislamiento: una conexión pertenece a un único proyecto y toda consulta recorre
la cadena proyecto → usuario (§53, ADR-005).
"""

from __future__ import annotations

import datetime as dt
import secrets
import uuid
from typing import Any

import sqlalchemy as sa
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from softree_audit.core.config import Settings
from softree_audit.core.crypto import DecryptionError, SecretBox
from softree_audit.core.errors import AppError, NotFoundError
from softree_audit.core.logging import get_logger
from softree_audit.core.redis import RedisClient
from softree_audit.models import ConnectionStatus, Project, SearchConsoleConnection
from softree_audit.services.search_console.client import SearchConsoleClient
from softree_audit.services.search_console.oauth import (
    OAuthCredentials,
    OAuthError,
    OAuthNotConfiguredError,
    RefreshTokenRevokedError,
    authorization_url,
    exchange_code,
    refresh_access_token,
)

logger = get_logger(__name__)

# El `state` vive lo justo para completar el consentimiento.
STATE_TTL_SECONDS = 600


class IntegrationNotConfiguredError(AppError):
    status_code = 503
    code = "google_not_configured"
    message = (
        "La integración con Google no está configurada. Defina GOOGLE_CLIENT_ID y "
        "GOOGLE_CLIENT_SECRET."
    )


class InvalidOAuthStateError(AppError):
    status_code = 400
    code = "invalid_oauth_state"
    message = "La solicitud de conexión no es válida o caducó. Inicie el proceso de nuevo."


class ConnectionRevokedError(AppError):
    status_code = 409
    code = "google_connection_revoked"
    message = "El acceso a Google fue revocado. Vuelva a conectar la cuenta."


class NotConnectedError(AppError):
    status_code = 404
    code = "google_not_connected"
    message = "El proyecto no tiene una conexión con Search Console."


class GoogleIntegrationService:
    def __init__(
        self,
        session: AsyncSession,
        redis: RedisClient,
        settings: Settings,
        owner_id: uuid.UUID,
    ) -> None:
        self._session = session
        self._redis = redis
        self._settings = settings
        self._owner_id = owner_id
        self._box = SecretBox(settings.secret_key, settings.secret_key_previous)

    @property
    def credentials(self) -> OAuthCredentials:
        return OAuthCredentials(
            client_id=self._settings.google_client_id or "",
            client_secret=self._settings.google_client_secret or "",
            redirect_uri=self._settings.google_redirect_uri,
        )

    # ── Conexión ───────────────────────────────────────────────────────────

    async def start_connection(self, project_id: uuid.UUID) -> dict[str, str]:
        """Genera la URL de consentimiento y guarda el `state`."""
        await self._assert_project_owned(project_id)
        if not self.credentials.is_configured:
            raise IntegrationNotConfiguredError()

        # `state` aleatorio ligado a usuario y proyecto: impide que un tercero
        # complete el flujo por nosotros o lo asocie a otro proyecto.
        state = secrets.token_urlsafe(32)
        try:
            await self._redis.set(
                self._state_key(state),
                f"{self._owner_id}:{project_id}",
                ex=STATE_TTL_SECONDS,
            )
        except RedisError as exc:
            raise IntegrationNotConfiguredError(
                "No fue posible iniciar la conexión: el almacén de sesión no responde."
            ) from exc

        logger.info("google.connection_started", project_id=str(project_id))
        return {"authorization_url": authorization_url(self.credentials, state), "state": state}

    async def complete_connection(self, code: str, state: str) -> SearchConsoleConnection:
        """Canjea el código y guarda el refresh token cifrado."""
        project_id = await self._consume_state(state)

        try:
            tokens = await exchange_code(self.credentials, code)
        except OAuthNotConfiguredError as exc:
            raise IntegrationNotConfiguredError() from exc
        except OAuthError as exc:
            logger.warning("google.exchange_failed", reason=exc.reason)
            raise InvalidOAuthStateError(f"Google rechazó la autorización ({exc.reason}).") from exc

        if not tokens.refresh_token:
            # Sin refresh token la conexión moriría en una hora.
            raise InvalidOAuthStateError(
                "Google no devolvió un token de actualización. Revoque el acceso previo en "
                "la cuenta de Google y vuelva a conectar."
            )

        account_email = await self._account_email(tokens.access_token)
        connection = await self._get_connection(project_id)

        if connection is None:
            connection = SearchConsoleConnection(
                project_id=project_id,
                refresh_token_encrypted=self._box.encrypt(tokens.refresh_token),
                scopes=list((tokens.scope or "").split()) or ["webmasters.readonly"],
                google_account_email=account_email,
                status=ConnectionStatus.CONNECTED,
            )
            self._session.add(connection)
        else:
            connection.refresh_token_encrypted = self._box.encrypt(tokens.refresh_token)
            connection.scopes = list((tokens.scope or "").split()) or connection.scopes
            connection.google_account_email = account_email
            connection.status = ConnectionStatus.CONNECTED
            connection.last_error = None

        await self._session.flush()
        logger.info("google.connected", project_id=str(project_id))
        return connection

    async def disconnect(self, project_id: uuid.UUID) -> None:
        await self._assert_project_owned(project_id)
        connection = await self._get_connection(project_id)
        if connection is None:
            raise NotConnectedError()
        await self._session.delete(connection)
        await self._session.flush()
        logger.info("google.disconnected", project_id=str(project_id))

    async def status(self, project_id: uuid.UUID) -> dict[str, Any]:
        """Estado de la conexión.

        No estar conectado no es un error (§23): se responde 200 con el estado.
        """
        await self._assert_project_owned(project_id)
        connection = await self._get_connection(project_id)

        if connection is None:
            return {
                "status": "not_connected",
                "configured": self.credentials.is_configured,
                "project_id": project_id,
                "google_account_email": None,
                "property_url": None,
                "last_sync_at": None,
                "last_error": None,
            }

        return {
            "status": connection.status.value,
            "configured": self.credentials.is_configured,
            "project_id": project_id,
            "google_account_email": connection.google_account_email,
            "property_url": connection.property_url,
            "last_sync_at": connection.last_sync_at,
            "last_error": connection.last_error,
        }

    # ── Propiedades ────────────────────────────────────────────────────────

    async def list_properties(self, project_id: uuid.UUID) -> list[dict[str, str]]:
        access_token = await self.access_token_for(project_id)
        async with SearchConsoleClient(access_token) as client:
            return await client.list_properties()

    async def select_property(
        self, project_id: uuid.UUID, property_url: str
    ) -> SearchConsoleConnection:
        connection = await self._require_connection(project_id)

        available = {item["site_url"] for item in await self.list_properties(project_id)}
        if property_url not in available:
            raise NotFoundError(
                "La cuenta conectada no tiene acceso a esa propiedad de Search Console."
            )

        connection.property_url = property_url
        await self._session.flush()
        logger.info(
            "google.property_selected", project_id=str(project_id), property_url=property_url
        )
        return connection

    # ── Tokens ─────────────────────────────────────────────────────────────

    async def access_token_for(self, project_id: uuid.UUID) -> str:
        """Access token vigente. Se obtiene en memoria y no se persiste."""
        connection = await self._require_connection(project_id)

        try:
            refresh_token = self._box.decrypt(connection.refresh_token_encrypted)
        except DecryptionError as exc:
            connection.status = ConnectionStatus.ERROR
            connection.last_error = "No fue posible descifrar la credencial almacenada."
            # Se confirma antes de propagar: la petición terminará en error y su
            # rollback desharía el cambio de estado.
            await self._session.commit()
            raise ConnectionRevokedError(
                "La credencial guardada no puede descifrarse. Vuelva a conectar la cuenta."
            ) from exc

        try:
            tokens = await refresh_access_token(self.credentials, refresh_token)
        except RefreshTokenRevokedError as exc:
            connection.status = ConnectionStatus.REVOKED
            connection.last_error = str(exc)
            # Igual que arriba: la revocación debe persistir aunque la petición
            # devuelva 409, para que la interfaz pueda pedir reconectar.
            await self._session.commit()
            logger.warning("google.refresh_revoked", project_id=str(project_id))
            raise ConnectionRevokedError() from exc
        except OAuthError as exc:
            connection.last_error = str(exc)
            await self._session.commit()
            raise IntegrationNotConfiguredError(
                f"No fue posible renovar el acceso a Google: {exc}"
            ) from exc

        return tokens.access_token

    # ── Internos ───────────────────────────────────────────────────────────

    @staticmethod
    def _state_key(state: str) -> str:
        return f"google:oauth:state:{state}"

    async def _consume_state(self, state: str) -> uuid.UUID:
        """Valida y consume el `state`. Un `state` solo sirve una vez."""
        try:
            raw = await self._redis.get(self._state_key(state))
            if raw:
                await self._redis.delete(self._state_key(state))
        except RedisError as exc:
            raise InvalidOAuthStateError() from exc

        if not raw:
            raise InvalidOAuthStateError()

        owner, _, project = str(raw).partition(":")
        if uuid.UUID(owner) != self._owner_id:
            logger.warning("google.state_owner_mismatch")
            raise InvalidOAuthStateError()

        project_id = uuid.UUID(project)
        await self._assert_project_owned(project_id)
        return project_id

    async def _assert_project_owned(self, project_id: uuid.UUID) -> None:
        exists = await self._session.scalar(
            sa.select(sa.func.count())
            .select_from(Project)
            .where(Project.id == project_id, Project.owner_id == self._owner_id)
        )
        if not exists:
            raise NotFoundError("El proyecto no existe.")

    async def _get_connection(self, project_id: uuid.UUID) -> SearchConsoleConnection | None:
        result = await self._session.execute(
            sa.select(SearchConsoleConnection)
            .join(Project, Project.id == SearchConsoleConnection.project_id)
            .where(
                SearchConsoleConnection.project_id == project_id,
                Project.owner_id == self._owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def _require_connection(self, project_id: uuid.UUID) -> SearchConsoleConnection:
        await self._assert_project_owned(project_id)
        connection = await self._get_connection(project_id)
        if connection is None:
            raise NotConnectedError()
        if connection.status is ConnectionStatus.REVOKED:
            raise ConnectionRevokedError()
        return connection

    async def _account_email(self, access_token: str) -> str | None:
        """Correo de la cuenta conectada, solo para mostrarlo en la interfaz."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
                response = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if response.status_code == 200:
                email = response.json().get("email")
                return str(email) if email else None
        except (httpx.HTTPError, ValueError):
            # Es un dato de conveniencia: su ausencia no invalida la conexión.
            logger.info("google.userinfo_unavailable")
        return None

    async def mark_synced(self, project_id: uuid.UUID) -> None:
        connection = await self._get_connection(project_id)
        if connection is not None:
            connection.last_sync_at = dt.datetime.now(dt.UTC)
            await self._session.flush()
