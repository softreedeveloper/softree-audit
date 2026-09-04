"""Conexión con Google Search Console: estado, OAuth, aislamiento y métricas."""

from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
import sqlalchemy as sa
from httpx import AsyncClient
from softree_audit.core.crypto import SecretBox
from softree_audit.models import (
    ConnectionStatus,
    Project,
    SearchConsoleConnection,
    User,
)
from softree_audit.services.search_console.oauth import TOKEN_ENDPOINT
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

STATUS = "/api/v1/integrations/google/status"
CONNECT = "/api/v1/integrations/google/connect"
CALLBACK = "/api/v1/integrations/google/callback"
PROPERTIES = "/api/v1/integrations/google/properties"
PROPERTY = "/api/v1/integrations/google/property"
CONNECTION = "/api/v1/integrations/google/connection"

SITES_API = "https://www.googleapis.com/webmasters/v3/sites"
USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"


async def _project(client: AsyncClient, name: str = "Proyecto GSC") -> str:
    response = await client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    return str(response.json()["id"])


async def _connect(
    session: AsyncSession,
    project_id: uuid.UUID,
    secret_key: str,
    *,
    status: ConnectionStatus = ConnectionStatus.CONNECTED,
    property_url: str | None = "https://softree.mx/",
) -> SearchConsoleConnection:
    connection = SearchConsoleConnection(
        project_id=project_id,
        refresh_token_encrypted=SecretBox(secret_key).encrypt("1//04refresco"),
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        google_account_email="cuenta@softree.mx",
        property_url=property_url,
        status=status,
    )
    session.add(connection)
    await session.commit()
    return connection


def _configure_google(app: object, settings: object) -> object:
    """Configura credenciales de Google solo para la prueba en curso.

    Devuelve la configuración anterior, que la prueba debe restaurar.
    """
    from softree_audit.core.config import Settings

    original = app.state.settings  # type: ignore[attr-defined]
    app.state.settings = Settings(  # type: ignore[attr-defined]
        _env_file=None,
        app_env="development",
        secret_key=settings.secret_key,  # type: ignore[attr-defined]
        database_url=settings.database_url,  # type: ignore[attr-defined]
        redis_url=settings.redis_url,  # type: ignore[attr-defined]
        ssrf_allow_private_networks=False,
        google_client_id="cliente.apps.googleusercontent.com",
        google_client_secret="secreto",
    )
    return original


# ── Estado ─────────────────────────────────────────────────────────────────


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(f"{STATUS}?project_id={uuid.uuid4()}")).status_code == 401


async def test_not_connected_is_not_an_error(auth_client: AsyncClient) -> None:
    """Requisito §23: la ausencia de conexión se responde con 200."""
    project = await _project(auth_client)
    response = await auth_client.get(f"{STATUS}?project_id={project}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_connected"
    assert body["property_url"] is None


async def test_status_of_a_connected_project(
    auth_client: AsyncClient, app_context: tuple[object, AsyncSession], settings: object
) -> None:
    _, session = app_context
    project = await _project(auth_client)
    await _connect(session, uuid.UUID(project), settings.secret_key)  # type: ignore[attr-defined]

    body = (await auth_client.get(f"{STATUS}?project_id={project}")).json()
    assert body["status"] == "connected"
    assert body["google_account_email"] == "cuenta@softree.mx"
    assert body["property_url"] == "https://softree.mx/"


async def test_status_of_an_unknown_project_returns_404(auth_client: AsyncClient) -> None:
    assert (await auth_client.get(f"{STATUS}?project_id={uuid.uuid4()}")).status_code == 404


@pytest.mark.security
async def test_status_of_another_users_project_returns_404(
    auth_client: AsyncClient,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    _, session = app_context
    foreign = Project(owner_id=other_user.id, name="Ajeno")
    session.add(foreign)
    await session.commit()

    assert (await auth_client.get(f"{STATUS}?project_id={foreign.id}")).status_code == 404


# ── Inicio de la conexión ──────────────────────────────────────────────────


async def test_connect_without_google_credentials_returns_503(auth_client: AsyncClient) -> None:
    """Sin credenciales configuradas se dice claramente, no se falla en silencio."""
    project = await _project(auth_client)
    response = await auth_client.post(CONNECT, json={"project_id": project})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "google_not_configured"


@pytest.mark.security
async def test_connect_generates_a_single_use_state(
    auth_client: AsyncClient, app_context: tuple[object, AsyncSession], settings: object
) -> None:
    from softree_audit.core.config import Settings

    app, _ = app_context
    project = await _project(auth_client)

    # Se configura Google solo para esta prueba.
    configured = Settings(
        _env_file=None,
        app_env="development",
        secret_key=settings.secret_key,  # type: ignore[attr-defined]
        database_url=settings.database_url,  # type: ignore[attr-defined]
        redis_url=settings.redis_url,  # type: ignore[attr-defined]
        ssrf_allow_private_networks=False,
        google_client_id="cliente.apps.googleusercontent.com",
        google_client_secret="secreto",
    )
    app.state.settings = configured  # type: ignore[attr-defined]

    response = await auth_client.post(CONNECT, json={"project_id": project})
    assert response.status_code == 200

    body = response.json()
    params = parse_qs(urlsplit(body["authorization_url"]).query)
    assert params["state"][0] == body["state"]
    assert params["access_type"][0] == "offline"
    assert "readonly" in params["scope"][0]

    app.state.settings = settings  # type: ignore[attr-defined]


@pytest.mark.security
async def test_callback_with_an_unknown_state_is_rejected(client: AsyncClient) -> None:
    """Un `state` inventado no debe poder crear una conexión."""
    response = await client.get(f"{CALLBACK}?code=abc&state=inventado", follow_redirects=False)
    assert response.status_code == 303
    assert "google=error" in response.headers["location"]
    assert "reason=invalid_state" in response.headers["location"]


async def test_callback_with_an_error_redirects_to_the_interface(client: AsyncClient) -> None:
    response = await client.get(f"{CALLBACK}?error=access_denied", follow_redirects=False)
    assert response.status_code == 303
    assert "google=error" in response.headers["location"]
    assert "access_denied" in response.headers["location"]


@respx.mock
@pytest.mark.security
async def test_callback_completes_the_connection_without_authorization_header(
    auth_client: AsyncClient, app_context: tuple[object, AsyncSession], settings: object
) -> None:
    """Google devuelve al navegador sin cabecera `Authorization`.

    Es una navegación de primer nivel: no lleva el token de acceso, que vive en
    memoria del cliente, y tampoco la cookie de refresco, que es
    `SameSite=Strict` y está limitada a `/api/v1/auth`. Si el callback exigiera
    sesión, el flujo de OAuth sería imposible de completar desde un navegador.
    """
    app, session = app_context
    project = await _project(auth_client, "Proyecto callback")
    original = _configure_google(app, settings)

    try:
        response = await auth_client.post(CONNECT, json={"project_id": project})
        assert response.status_code == 200
        state = response.json()["state"]

        respx.post(TOKEN_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "ya29.callback",
                    "expires_in": 3599,
                    "refresh_token": "1//04callback",
                    "scope": "https://www.googleapis.com/auth/webmasters.readonly",
                },
            )
        )
        respx.get(USERINFO).mock(
            return_value=httpx.Response(200, json={"email": "cuenta@softree.mx"})
        )

        # Se retira la cabecera: así es como llega el navegador.
        del auth_client.headers["Authorization"]
        callback = await auth_client.get(
            f"{CALLBACK}?code=codigo-de-google&state={state}", follow_redirects=False
        )
    finally:
        app.state.settings = original  # type: ignore[attr-defined]

    assert callback.status_code == 303
    location = callback.headers["location"]
    assert "google=connected" in location
    assert project in location

    connection = await session.scalar(
        sa.select(SearchConsoleConnection).where(
            SearchConsoleConnection.project_id == uuid.UUID(project)
        )
    )
    assert connection is not None
    assert connection.status is ConnectionStatus.CONNECTED
    assert connection.google_account_email == "cuenta@softree.mx"
    # El refresh token se guarda cifrado, nunca en claro.
    assert b"1//04callback" not in connection.refresh_token_encrypted
    assert (
        SecretBox(settings.secret_key).decrypt(  # type: ignore[attr-defined]
            connection.refresh_token_encrypted
        )
        == "1//04callback"
    )


@pytest.mark.security
async def test_a_state_can_only_be_used_once(
    auth_client: AsyncClient, app_context: tuple[object, AsyncSession], settings: object
) -> None:
    """El segundo intento con el mismo `state` no puede volver a canjearse."""
    app, _ = app_context
    project = await _project(auth_client, "Proyecto state")
    original = _configure_google(app, settings)

    try:
        state = (await auth_client.post(CONNECT, json={"project_id": project})).json()["state"]
        del auth_client.headers["Authorization"]

        with respx.mock:
            respx.post(TOKEN_ENDPOINT).mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "access_token": "ya29.uno",
                        "expires_in": 3599,
                        "refresh_token": "1//04uno",
                    },
                )
            )
            respx.get(USERINFO).mock(
                return_value=httpx.Response(200, json={"email": "cuenta@softree.mx"})
            )
            first = await auth_client.get(
                f"{CALLBACK}?code=uno&state={state}", follow_redirects=False
            )

        second = await auth_client.get(f"{CALLBACK}?code=dos&state={state}", follow_redirects=False)
    finally:
        app.state.settings = original  # type: ignore[attr-defined]

    assert "google=connected" in first.headers["location"]
    assert second.status_code == 303
    assert "reason=invalid_state" in second.headers["location"]


# ── Propiedades y desconexión ──────────────────────────────────────────────


@respx.mock
async def test_list_properties_of_a_connected_project(
    auth_client: AsyncClient, app_context: tuple[object, AsyncSession], settings: object
) -> None:
    _, session = app_context
    project = await _project(auth_client)
    await _connect(session, uuid.UUID(project), settings.secret_key)  # type: ignore[attr-defined]

    respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"access_token": "ya29.x", "expires_in": 3599})
    )
    respx.get(SITES_API).mock(
        return_value=httpx.Response(
            200,
            json={
                "siteEntry": [{"siteUrl": "https://softree.mx/", "permissionLevel": "siteOwner"}]
            },
        )
    )

    response = await auth_client.get(f"{PROPERTIES}?project_id={project}")
    assert response.status_code == 200
    assert response.json()[0]["site_url"] == "https://softree.mx/"


@respx.mock
@pytest.mark.security
async def test_a_property_the_account_cannot_access_is_rejected(
    auth_client: AsyncClient, app_context: tuple[object, AsyncSession], settings: object
) -> None:
    _, session = app_context
    project = await _project(auth_client)
    await _connect(session, uuid.UUID(project), settings.secret_key)  # type: ignore[attr-defined]

    respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"access_token": "ya29.x", "expires_in": 3599})
    )
    respx.get(SITES_API).mock(return_value=httpx.Response(200, json={"siteEntry": []}))

    response = await auth_client.put(
        PROPERTY, json={"project_id": project, "property_url": "https://ajeno.test/"}
    )
    assert response.status_code == 404


@respx.mock
@pytest.mark.security
async def test_revoked_access_marks_the_connection_and_returns_409(
    auth_client: AsyncClient, app_context: tuple[object, AsyncSession], settings: object
) -> None:
    _, session = app_context
    project = await _project(auth_client)
    connection = await _connect(session, uuid.UUID(project), settings.secret_key)  # type: ignore[attr-defined]

    respx.post(TOKEN_ENDPOINT).mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )

    response = await auth_client.get(f"{PROPERTIES}?project_id={project}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "google_connection_revoked"

    await session.refresh(connection)
    assert connection.status is ConnectionStatus.REVOKED


async def test_disconnect(
    auth_client: AsyncClient, app_context: tuple[object, AsyncSession], settings: object
) -> None:
    _, session = app_context
    project = await _project(auth_client)
    await _connect(session, uuid.UUID(project), settings.secret_key)  # type: ignore[attr-defined]

    assert (await auth_client.delete(f"{CONNECTION}?project_id={project}")).status_code == 204
    assert (await auth_client.get(f"{STATUS}?project_id={project}")).json()["status"] == (
        "not_connected"
    )


async def test_disconnect_without_connection_returns_404(auth_client: AsyncClient) -> None:
    project = await _project(auth_client)
    assert (await auth_client.delete(f"{CONNECTION}?project_id={project}")).status_code == 404


@pytest.mark.security
async def test_refresh_token_is_stored_encrypted(
    auth_client: AsyncClient, app_context: tuple[object, AsyncSession], settings: object
) -> None:
    """`security.md` §7: la credencial nunca se guarda en claro."""
    _, session = app_context
    project = await _project(auth_client)
    connection = await _connect(session, uuid.UUID(project), settings.secret_key)  # type: ignore[attr-defined]

    stored = bytes(connection.refresh_token_encrypted)
    assert b"1//04refresco" not in stored
    assert SecretBox(settings.secret_key).decrypt(stored) == "1//04refresco"  # type: ignore[attr-defined]


@pytest.mark.security
async def test_the_api_never_returns_the_refresh_token(
    auth_client: AsyncClient, app_context: tuple[object, AsyncSession], settings: object
) -> None:
    _, session = app_context
    project = await _project(auth_client)
    await _connect(session, uuid.UUID(project), settings.secret_key)  # type: ignore[attr-defined]

    response = await auth_client.get(f"{STATUS}?project_id={project}")
    assert "refresh" not in response.text.lower()
    assert "1//04" not in response.text


@pytest.mark.security
async def test_connections_are_isolated_between_projects(
    auth_client: AsyncClient, app_context: tuple[object, AsyncSession], settings: object
) -> None:
    """§53: los datos pertenecen a la propiedad autorizada de cada proyecto."""
    _, session = app_context
    connected = await _project(auth_client, "Con conexión")
    other = await _project(auth_client, "Sin conexión")
    await _connect(session, uuid.UUID(connected), settings.secret_key)  # type: ignore[attr-defined]

    assert (await auth_client.get(f"{STATUS}?project_id={other}")).json()["status"] == (
        "not_connected"
    )
    assert (await auth_client.get(f"{PROPERTIES}?project_id={other}")).status_code == 404


# ── Métricas del scan ──────────────────────────────────────────────────────


async def test_scan_search_console_without_module_reports_it(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    from tests.integration.test_findings import _seed

    _, session = app_context
    _, scan = await _seed(session, user)

    body = (await auth_client.get(f"/api/v1/scans/{scan.id}/search-console")).json()
    assert body["module_status"] == "no_ejecutado"
    assert body["metrics"] == []


async def test_scan_search_console_returns_metrics(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    from softree_audit.models import (
        ModuleName,
        ModuleStatus,
        ScanModuleRun,
        SearchConsoleDimension,
        SearchConsoleMetric,
        SearchConsolePeriod,
    )

    from tests.integration.test_findings import _seed

    _, session = app_context
    _, scan = await _seed(session, user)

    session.add(
        ScanModuleRun(
            scan_id=scan.id,
            module=ModuleName.SEARCH_CONSOLE,
            status=ModuleStatus.COMPLETED,
            detail={
                "property_url": "https://softree.mx/",
                "totals": {"28d": {"clicks": 120, "impressions": 4300}},
            },
        )
    )
    for index in range(3):
        session.add(
            SearchConsoleMetric(
                scan_id=scan.id,
                period=SearchConsolePeriod.LAST_28_DAYS,
                dimension=SearchConsoleDimension.QUERY,
                dimension_value=f"consulta {index}",
                clicks=10 - index,
                impressions=100,
                ctr=0.1,
                position=4.5,
            )
        )
    await session.commit()

    body = (
        await auth_client.get(f"/api/v1/scans/{scan.id}/search-console?period=28d&dimension=query")
    ).json()

    assert body["module_status"] == "completed"
    assert body["property_url"] == "https://softree.mx/"
    assert body["totals"]["28d"]["clicks"] == 120
    assert len(body["metrics"]) == 3
    # Ordenadas por clics: lo que más tráfico trae, primero.
    assert body["metrics"][0]["clicks"] == 10


@pytest.mark.security
async def test_scan_metrics_of_another_user_are_not_reachable(
    auth_client: AsyncClient,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    from tests.integration.test_findings import _seed

    _, session = app_context
    _, scan = await _seed(session, other_user)
    assert (await auth_client.get(f"/api/v1/scans/{scan.id}/search-console")).status_code == 404


async def test_a_date_period_filter_returns_only_that_period(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    from softree_audit.models import (
        SearchConsoleDimension,
        SearchConsoleMetric,
        SearchConsolePeriod,
    )

    from tests.integration.test_findings import _seed

    _, session = app_context
    _, scan = await _seed(session, user)

    for period in (SearchConsolePeriod.LAST_7_DAYS, SearchConsolePeriod.LAST_28_DAYS):
        session.add(
            SearchConsoleMetric(
                scan_id=scan.id,
                period=period,
                dimension=SearchConsoleDimension.DEVICE,
                dimension_value="MOBILE",
                clicks=5,
                impressions=50,
                ctr=0.1,
                position=3.0,
            )
        )
    await session.commit()

    body = (
        await auth_client.get(f"/api/v1/scans/{scan.id}/search-console?period=7d&dimension=device")
    ).json()
    assert len(body["metrics"]) == 1
    assert body["metrics"][0]["period"] == "7d"
