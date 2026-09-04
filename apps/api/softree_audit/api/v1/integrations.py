"""Endpoints de integraciones externas (Google Search Console)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse

from softree_audit.api.deps import AppSettings, CurrentUser, DbSession
from softree_audit.core.redis import RedisClient
from softree_audit.integrations.google import GoogleIntegrationService
from softree_audit.schemas.common import ErrorResponse
from softree_audit.schemas.integration import (
    GoogleConnectRequest,
    GoogleConnectResponse,
    GoogleProperty,
    GooglePropertySelection,
    GoogleStatusResponse,
)

router = APIRouter(prefix="/integrations/google", tags=["integrations"])

# A dónde vuelve el navegador tras el consentimiento.
CALLBACK_REDIRECT = "/integrations"


def get_redis_client(request: Request) -> RedisClient:
    redis: RedisClient = request.app.state.redis
    return redis


def get_service(
    session: DbSession,
    user: CurrentUser,
    settings: AppSettings,
    redis: Annotated[RedisClient, Depends(get_redis_client)],
) -> GoogleIntegrationService:
    return GoogleIntegrationService(session, redis, settings, user.id)


ServiceDep = Annotated[GoogleIntegrationService, Depends(get_service)]


@router.get(
    "/status",
    response_model=GoogleStatusResponse,
    summary="Estado de la conexión con Search Console",
)
async def connection_status(project_id: uuid.UUID, service: ServiceDep) -> GoogleStatusResponse:
    """No estar conectado no es un error: se responde 200 con el estado (§23)."""
    return GoogleStatusResponse.model_validate(await service.status(project_id))


@router.post(
    "/connect",
    response_model=GoogleConnectResponse,
    summary="Iniciar la conexión con Google",
    responses={
        404: {"model": ErrorResponse, "description": "El proyecto no existe"},
        503: {"model": ErrorResponse, "description": "La integración no está configurada"},
    },
)
async def connect(payload: GoogleConnectRequest, service: ServiceDep) -> GoogleConnectResponse:
    return GoogleConnectResponse.model_validate(await service.start_connection(payload.project_id))


@router.get(
    "/callback",
    summary="Callback de OAuth",
    include_in_schema=False,
)
async def callback(
    service: ServiceDep,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Recibe la respuesta de Google y devuelve al usuario a la interfaz.

    Los errores viajan en la URL como un código breve, no como texto de Google:
    la interfaz los traduce.
    """
    if error or not code or not state:
        return RedirectResponse(
            f"{CALLBACK_REDIRECT}?google=error&reason={error or 'missing_code'}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    connection = await service.complete_connection(code, state)
    return RedirectResponse(
        f"{CALLBACK_REDIRECT}?google=connected&project_id={connection.project_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get(
    "/properties",
    response_model=list[GoogleProperty],
    summary="Propiedades disponibles en la cuenta conectada",
    responses={
        404: {"model": ErrorResponse, "description": "El proyecto no existe o no está conectado"},
        409: {"model": ErrorResponse, "description": "El acceso a Google fue revocado"},
    },
)
async def properties(project_id: uuid.UUID, service: ServiceDep) -> list[GoogleProperty]:
    return [
        GoogleProperty.model_validate(item) for item in await service.list_properties(project_id)
    ]


@router.put(
    "/property",
    response_model=GoogleStatusResponse,
    summary="Seleccionar la propiedad del proyecto",
    responses={
        404: {
            "model": ErrorResponse,
            "description": (
                "El proyecto no existe, no está conectado, o la propiedad no es accesible"
            ),
        }
    },
)
async def select_property(
    payload: GooglePropertySelection, service: ServiceDep
) -> GoogleStatusResponse:
    await service.select_property(payload.project_id, payload.property_url)
    return GoogleStatusResponse.model_validate(await service.status(payload.project_id))


@router.delete(
    "/connection",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desconectar la cuenta de Google",
    responses={404: {"model": ErrorResponse, "description": "El proyecto no está conectado"}},
)
async def disconnect(project_id: uuid.UUID, service: ServiceDep) -> None:
    await service.disconnect(project_id)
