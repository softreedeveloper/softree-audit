"""CRUD de proyectos y aislamiento entre cuentas."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from softree_audit.core.security import hash_password
from softree_audit.models import Project, User
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

PROJECTS = "/api/v1/projects"


async def _create(client: AsyncClient, name: str = "Demo Project") -> dict[str, object]:
    response = await client.post(PROJECTS, json={"name": name})
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(PROJECTS)).status_code == 401
    assert (await client.post(PROJECTS, json={"name": "X"})).status_code == 401


async def test_create_and_read(auth_client: AsyncClient) -> None:
    created = await _create(auth_client)
    assert created["name"] == "Demo Project"
    assert created["sites_count"] == 0

    response = await auth_client.get(f"{PROJECTS}/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_list_is_empty_at_the_start(auth_client: AsyncClient) -> None:
    response = await auth_client.get(PROJECTS)
    assert response.status_code == 200
    assert response.json() == {"items": [], "next_cursor": None, "total": 0}


async def test_update(auth_client: AsyncClient) -> None:
    created = await _create(auth_client)
    response = await auth_client.put(
        f"{PROJECTS}/{created['id']}",
        json={"name": "Demo renombrado", "client_name": "Cliente S.A.", "notes": "nota"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Demo renombrado"
    assert body["client_name"] == "Cliente S.A."


async def test_delete(auth_client: AsyncClient) -> None:
    created = await _create(auth_client)
    assert (await auth_client.delete(f"{PROJECTS}/{created['id']}")).status_code == 204
    assert (await auth_client.get(f"{PROJECTS}/{created['id']}")).status_code == 404


async def test_duplicate_name_is_rejected(auth_client: AsyncClient) -> None:
    await _create(auth_client)
    response = await auth_client.post(PROJECTS, json={"name": "Demo Project"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_name_is_required(auth_client: AsyncClient) -> None:
    response = await auth_client.post(PROJECTS, json={"name": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_unknown_fields_are_rejected(auth_client: AsyncClient) -> None:
    response = await auth_client.post(PROJECTS, json={"name": "X", "owner_id": str(uuid.uuid4())})
    assert response.status_code == 422


async def test_unknown_project_returns_404(auth_client: AsyncClient) -> None:
    response = await auth_client.get(f"{PROJECTS}/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_malformed_id_returns_422(auth_client: AsyncClient) -> None:
    assert (await auth_client.get(f"{PROJECTS}/no-es-un-uuid")).status_code == 422


async def test_pagination_with_cursor(auth_client: AsyncClient) -> None:
    for index in range(5):
        await _create(auth_client, f"Proyecto {index}")

    first = (await auth_client.get(f"{PROJECTS}?limit=2")).json()
    assert len(first["items"]) == 2
    assert first["total"] == 5
    assert first["next_cursor"]

    second = (await auth_client.get(f"{PROJECTS}?limit=2&cursor={first['next_cursor']}")).json()
    assert len(second["items"]) == 2

    third = (await auth_client.get(f"{PROJECTS}?limit=2&cursor={second['next_cursor']}")).json()
    assert len(third["items"]) == 1
    assert third["next_cursor"] is None

    seen = [item["id"] for page in (first, second, third) for item in page["items"]]
    assert len(set(seen)) == 5


async def test_invalid_cursor_returns_400(auth_client: AsyncClient) -> None:
    response = await auth_client.get(f"{PROJECTS}?cursor=no-es-un-cursor")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_cursor"


async def test_limit_is_bounded(auth_client: AsyncClient) -> None:
    assert (await auth_client.get(f"{PROJECTS}?limit=101")).status_code == 422
    assert (await auth_client.get(f"{PROJECTS}?limit=0")).status_code == 422


@pytest.mark.security
async def test_projects_of_other_users_are_invisible(
    auth_client: AsyncClient,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    """Un identificador ajeno devuelve 404, no 403: no se confirma que exista."""
    _, session = app_context
    foreign = Project(owner_id=other_user.id, name="Proyecto ajeno")
    session.add(foreign)
    await session.commit()

    listing = (await auth_client.get(PROJECTS)).json()
    assert listing["total"] == 0

    assert (await auth_client.get(f"{PROJECTS}/{foreign.id}")).status_code == 404
    assert (
        await auth_client.put(f"{PROJECTS}/{foreign.id}", json={"name": "secuestrado"})
    ).status_code == 404
    assert (await auth_client.delete(f"{PROJECTS}/{foreign.id}")).status_code == 404


@pytest.mark.security
async def test_owner_cannot_be_forged(auth_client: AsyncClient, other_user: User) -> None:
    """El propietario sale del token, nunca del cuerpo de la petición."""
    response = await auth_client.post(
        PROJECTS, json={"name": "Intento", "owner_id": str(other_user.id)}
    )
    assert response.status_code == 422


async def test_two_users_can_reuse_the_same_project_name(
    auth_client: AsyncClient,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    """La unicidad del nombre es por propietario, no global."""
    _, session = app_context
    session.add(Project(owner_id=other_user.id, name="Demo Project"))
    await session.commit()

    assert (await auth_client.post(PROJECTS, json={"name": "Demo Project"})).status_code == 201


async def test_delete_requires_force_when_the_project_has_sites(
    auth_client: AsyncClient,
) -> None:
    project = await _create(auth_client)
    site = await auth_client.post(
        "/api/v1/sites",
        json={
            "project_id": project["id"],
            "name": "Sitio",
            "base_url": "https://softree.mx",
        },
    )
    assert site.status_code == 201

    blocked = await auth_client.delete(f"{PROJECTS}/{project['id']}")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "project_has_sites"
    assert blocked.json()["error"]["details"]["sites_count"] == 1

    forced = await auth_client.delete(f"{PROJECTS}/{project['id']}?force=true")
    assert forced.status_code == 204
    assert (await auth_client.get(f"/api/v1/sites/{site.json()['id']}")).status_code == 404


async def test_sites_count_is_reported(auth_client: AsyncClient) -> None:
    project = await _create(auth_client)
    await auth_client.post(
        "/api/v1/sites",
        json={"project_id": project["id"], "name": "Sitio", "base_url": "https://softree.mx"},
    )
    response = await auth_client.get(f"{PROJECTS}/{project['id']}")
    assert response.json()["sites_count"] == 1


async def test_password_hash_is_never_exposed(
    auth_client: AsyncClient, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    session.add(
        User(
            email="tercero@softree.test",
            full_name="Tercero",
            password_hash=hash_password("contrasena-de-prueba-larga"),
        )
    )
    await session.commit()

    response = await auth_client.get(PROJECTS)
    assert "argon2" not in response.text
