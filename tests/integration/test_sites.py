"""CRUD de sitios y gestión del scope."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from httpx import AsyncClient
from softree_audit.models import Project, User
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

PROJECTS = "/api/v1/projects"
SITES = "/api/v1/sites"


async def _project(client: AsyncClient, name: str = "Demo Project") -> str:
    response = await client.post(PROJECTS, json={"name": name})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _site(
    client: AsyncClient,
    project_id: str,
    *,
    base_url: str = "https://softree.mx",
    name: str = "Sitio corporativo",
    authorized: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "project_id": project_id,
        "name": name,
        "base_url": base_url,
    }
    if authorized:
        payload["authorized_by"] = "Cliente S.A."
        payload["authorization_date"] = str(dt.date(2026, 1, 15))
    response = await client.post(SITES, json=payload)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(SITES)).status_code == 401


async def test_create_normalizes_the_url_and_bootstraps_the_scope(
    auth_client: AsyncClient,
) -> None:
    project = await _project(auth_client)
    site = await _site(auth_client, project, base_url="HTTPS://Softree.MX:443/")

    assert site["base_url"] == "https://softree.mx"
    scope = site["scope"]
    assert isinstance(scope, dict)
    # El scope nace acotado al host del sitio y con valores por defecto seguros.
    assert scope["allowed_domains"] == ["softree.mx"]
    assert scope["max_pages"] == 200
    assert scope["max_depth"] == 3
    assert scope["respect_robots"] is True


async def test_site_without_authorization_is_not_scannable(auth_client: AsyncClient) -> None:
    project = await _project(auth_client)
    site = await _site(auth_client, project)
    assert site["is_authorized"] is False


async def test_authorized_site_is_scannable(auth_client: AsyncClient) -> None:
    project = await _project(auth_client)
    site = await _site(auth_client, project, authorized=True)
    assert site["is_authorized"] is True
    assert site["authorized_by"] == "Cliente S.A."


@pytest.mark.security
async def test_partial_authorization_is_rejected(auth_client: AsyncClient) -> None:
    project = await _project(auth_client)
    response = await auth_client.post(
        SITES,
        json={
            "project_id": project,
            "name": "Sitio",
            "base_url": "https://softree.mx",
            "authorized_by": "Cliente S.A.",
        },
    )
    assert response.status_code == 422


async def test_duplicate_url_in_the_same_project_is_rejected(auth_client: AsyncClient) -> None:
    project = await _project(auth_client)
    await _site(auth_client, project)
    response = await auth_client.post(
        SITES, json={"project_id": project, "name": "Otro", "base_url": "https://softree.mx/"}
    )
    assert response.status_code == 409


async def test_same_url_in_another_project_is_allowed(auth_client: AsyncClient) -> None:
    first = await _project(auth_client, "Proyecto A")
    second = await _project(auth_client, "Proyecto B")
    await _site(auth_client, first)
    await _site(auth_client, second)


async def test_list_filters_by_project(auth_client: AsyncClient) -> None:
    first = await _project(auth_client, "Proyecto A")
    second = await _project(auth_client, "Proyecto B")
    await _site(auth_client, first, base_url="https://a.softree.mx")
    await _site(auth_client, second, base_url="https://b.softree.mx")

    listing = (await auth_client.get(f"{SITES}?project_id={first}")).json()
    assert listing["total"] == 1
    assert listing["items"][0]["base_url"] == "https://a.softree.mx"

    everything = (await auth_client.get(SITES)).json()
    assert everything["total"] == 2


async def test_update_site(auth_client: AsyncClient) -> None:
    project = await _project(auth_client)
    site = await _site(auth_client, project)

    response = await auth_client.put(
        f"{SITES}/{site['id']}",
        json={
            "name": "Sitio renombrado",
            "base_url": "https://softree.mx",
            "authorized_by": "Cliente S.A.",
            "authorization_date": str(dt.date(2026, 2, 1)),
            "is_active": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Sitio renombrado"
    assert response.json()["is_authorized"] is True


async def test_changing_the_host_realigns_the_scope(auth_client: AsyncClient) -> None:
    """Un scope heredado dejaría de cubrir el sitio tras cambiar de dominio."""
    project = await _project(auth_client)
    site = await _site(auth_client, project)

    response = await auth_client.put(
        f"{SITES}/{site['id']}",
        json={"name": "Sitio", "base_url": "https://nuevo.example.com", "is_active": True},
    )
    assert response.status_code == 200
    assert response.json()["scope"]["allowed_domains"] == ["nuevo.example.com"]


async def test_delete_site(auth_client: AsyncClient) -> None:
    project = await _project(auth_client)
    site = await _site(auth_client, project)
    assert (await auth_client.delete(f"{SITES}/{site['id']}")).status_code == 204
    assert (await auth_client.get(f"{SITES}/{site['id']}")).status_code == 404


async def test_site_in_unknown_project_returns_404(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        SITES,
        json={"project_id": str(uuid.uuid4()), "name": "X", "base_url": "https://softree.mx"},
    )
    assert response.status_code == 404


@pytest.mark.security
async def test_cannot_attach_a_site_to_another_users_project(
    auth_client: AsyncClient,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    _, session = app_context
    foreign = Project(owner_id=other_user.id, name="Proyecto ajeno")
    session.add(foreign)
    await session.commit()

    response = await auth_client.post(
        SITES,
        json={"project_id": str(foreign.id), "name": "X", "base_url": "https://softree.mx"},
    )
    assert response.status_code == 404


@pytest.mark.security
@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://softree.mx",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://admin:secreto@softree.mx",
        "https://softree.mx@malicioso.test",
        "softree.mx",
    ],
)
async def test_invalid_base_urls_are_rejected(auth_client: AsyncClient, base_url: str) -> None:
    project = await _project(auth_client)
    response = await auth_client.post(
        SITES, json={"project_id": project, "name": "X", "base_url": base_url}
    )
    assert response.status_code == 422


# ── Scope ──────────────────────────────────────────────────────────────────


async def test_read_scope(auth_client: AsyncClient) -> None:
    project = await _project(auth_client)
    site = await _site(auth_client, project)
    response = await auth_client.get(f"{SITES}/{site['id']}/scope")
    assert response.status_code == 200
    assert response.json()["allowed_domains"] == ["softree.mx"]


async def test_update_scope(auth_client: AsyncClient) -> None:
    project = await _project(auth_client)
    site = await _site(auth_client, project)

    response = await auth_client.put(
        f"{SITES}/{site['id']}/scope",
        json={
            "allowed_domains": ["softree.mx", "WWW.Softree.MX"],
            "allowed_paths": ["/blog/"],
            "excluded_paths": ["/admin"],
            "max_pages": 50,
            "max_depth": 2,
            "timeout_seconds": 15,
            "request_delay_ms": 500,
            "concurrency": 2,
            "respect_robots": True,
            "zap_spider_enabled": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["allowed_domains"] == ["softree.mx", "www.softree.mx"]
    assert body["allowed_paths"] == ["/blog"]
    assert body["max_pages"] == 50
    assert body["zap_spider_enabled"] is False


@pytest.mark.security
async def test_scope_must_cover_the_site_host(auth_client: AsyncClient) -> None:
    """Un scope que no cubre el sitio haría el scan inútil o fuera de alcance."""
    project = await _project(auth_client)
    site = await _site(auth_client, project)

    response = await auth_client.put(
        f"{SITES}/{site['id']}/scope",
        json={"allowed_domains": ["otro-dominio.test"]},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "scope_excludes_site"


async def test_scope_rejects_paths_in_both_lists(auth_client: AsyncClient) -> None:
    project = await _project(auth_client)
    site = await _site(auth_client, project)

    response = await auth_client.put(
        f"{SITES}/{site['id']}/scope",
        json={
            "allowed_domains": ["softree.mx"],
            "allowed_paths": ["/blog"],
            "excluded_paths": ["/blog"],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "scope_path_conflict"


@pytest.mark.security
async def test_scope_limits_cannot_be_exceeded(auth_client: AsyncClient) -> None:
    project = await _project(auth_client)
    site = await _site(auth_client, project)

    response = await auth_client.put(
        f"{SITES}/{site['id']}/scope",
        json={"allowed_domains": ["softree.mx"], "max_pages": 999_999, "concurrency": 512},
    )
    assert response.status_code == 422


async def test_scope_limits_endpoint(auth_client: AsyncClient) -> None:
    response = await auth_client.get(f"{SITES}/scope-limits")
    assert response.status_code == 200
    body = response.json()
    assert body["max_pages"] == 5000
    assert body["concurrency"] == 16


@pytest.mark.security
async def test_scope_of_another_users_site_is_not_reachable(
    auth_client: AsyncClient,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    _, session = app_context
    foreign_project = Project(owner_id=other_user.id, name="Proyecto ajeno")
    session.add(foreign_project)
    await session.commit()

    from softree_audit.models import Scope, Site

    foreign_site = Site(project_id=foreign_project.id, name="Ajeno", base_url="https://ajeno.test")
    foreign_site.scope = Scope(allowed_domains=["ajeno.test"])
    session.add(foreign_site)
    await session.commit()

    assert (await auth_client.get(f"{SITES}/{foreign_site.id}")).status_code == 404
    assert (await auth_client.get(f"{SITES}/{foreign_site.id}/scope")).status_code == 404
    assert (
        await auth_client.put(
            f"{SITES}/{foreign_site.id}/scope", json={"allowed_domains": ["ajeno.test"]}
        )
    ).status_code == 404
