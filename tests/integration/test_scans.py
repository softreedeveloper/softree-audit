"""Alta, consulta y cancelación de auditorías."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from httpx import AsyncClient
from softree_audit.models import Project, ScanStatus, Scope, Site, User
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

PROJECTS = "/api/v1/projects"
SITES = "/api/v1/sites"
SCANS = "/api/v1/scans"


async def _authorized_site(
    client: AsyncClient, *, base_url: str = "https://softree.mx", authorized: bool = True
) -> dict[str, object]:
    project = await client.post(PROJECTS, json={"name": f"Proyecto {uuid.uuid4().hex[:6]}"})
    assert project.status_code == 201

    payload: dict[str, object] = {
        "project_id": project.json()["id"],
        "name": "Sitio",
        "base_url": base_url,
    }
    if authorized:
        payload["authorized_by"] = "Cliente S.A."
        payload["authorization_date"] = str(dt.date(2026, 1, 15))

    site = await client.post(SITES, json=payload)
    assert site.status_code == 201, site.text
    return dict(site.json())


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(SCANS)).status_code == 401
    assert (await client.post(SCANS, json={"site_id": str(uuid.uuid4())})).status_code == 401


@pytest.mark.security
async def test_unauthorized_site_cannot_be_scanned(auth_client: AsyncClient) -> None:
    """Control central: sin autorización registrada no se audita (§security.md §1)."""
    site = await _authorized_site(auth_client, authorized=False)
    response = await auth_client.post(SCANS, json={"site_id": site["id"]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "site_not_authorized"


@pytest.mark.security
async def test_inactive_site_cannot_be_scanned(auth_client: AsyncClient) -> None:
    site = await _authorized_site(auth_client)
    await auth_client.put(
        f"{SITES}/{site['id']}",
        json={
            "name": "Sitio",
            "base_url": str(site["base_url"]),
            "authorized_by": "Cliente S.A.",
            "authorization_date": str(dt.date(2026, 1, 15)),
            "is_active": False,
        },
    )
    response = await auth_client.post(SCANS, json={"site_id": site["id"]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "site_inactive"


@pytest.mark.security
async def test_target_resolving_to_a_private_address_is_rejected_at_creation(
    auth_client: AsyncClient,
    app_context: tuple[object, AsyncSession],
    user: User,
) -> None:
    """El guard rechaza antes de encolar: no se gasta un worker en un destino vetado."""
    _, session = app_context
    project = Project(owner_id=user.id, name="Interno")
    session.add(project)
    await session.flush()

    site = Site(
        project_id=project.id,
        name="Localhost",
        base_url="http://127.0.0.1",
        authorized_by="Softree",
        authorization_date=dt.date(2026, 1, 15),
    )
    site.scope = Scope(allowed_domains=["127.0.0.1"])
    session.add(site)
    await session.commit()

    response = await auth_client.post(SCANS, json={"site_id": str(site.id)})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "target_unreachable"
    assert body["error"]["details"]["reason"] == "blocked_network"


async def test_unknown_site_returns_404(auth_client: AsyncClient) -> None:
    response = await auth_client.post(SCANS, json={"site_id": str(uuid.uuid4())})
    assert response.status_code == 404


@pytest.mark.security
async def test_cannot_scan_another_users_site(
    auth_client: AsyncClient,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    _, session = app_context
    project = Project(owner_id=other_user.id, name="Ajeno")
    session.add(project)
    await session.flush()
    site = Site(
        project_id=project.id,
        name="Ajeno",
        base_url="https://ajeno.test",
        authorized_by="X",
        authorization_date=dt.date(2026, 1, 1),
    )
    site.scope = Scope(allowed_domains=["ajeno.test"])
    session.add(site)
    await session.commit()

    assert (await auth_client.post(SCANS, json={"site_id": str(site.id)})).status_code == 404


async def test_create_returns_202_and_enqueues(auth_client: AsyncClient) -> None:
    site = await _authorized_site(auth_client, base_url="https://example.com")
    response = await auth_client.post(SCANS, json={"site_id": site["id"], "scan_type": "full"})

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == ScanStatus.QUEUED.value
    assert body["progress"] == 0
    assert body["scan_type"] == "full"
    assert body["engine_version"]
    # El scope queda congelado en el scan para hacerlo reproducible.
    assert body["scope_snapshot"]["allowed_domains"] == ["example.com"]
    assert body["scope_snapshot"]["max_pages"] == 200


async def test_create_does_not_block_on_the_scan(auth_client: AsyncClient) -> None:
    """La respuesta llega antes de que exista ningún resultado."""
    site = await _authorized_site(auth_client, base_url="https://example.com")
    response = await auth_client.post(SCANS, json={"site_id": site["id"]})
    assert response.json()["pages_count"] == 0
    assert response.json()["finished_at"] is None


async def test_idempotency_key_returns_the_same_scan(auth_client: AsyncClient) -> None:
    """Contrato para n8n: reintentar el POST no lanza una segunda auditoría."""
    site = await _authorized_site(auth_client, base_url="https://example.com")
    headers = {"Idempotency-Key": "n8n-run-42"}

    first = await auth_client.post(SCANS, json={"site_id": site["id"]}, headers=headers)
    second = await auth_client.post(SCANS, json={"site_id": site["id"]}, headers=headers)

    assert first.status_code == 202
    assert second.json()["id"] == first.json()["id"]

    listing = (await auth_client.get(f"{SCANS}?site_id={site['id']}")).json()
    assert listing["total"] == 1


async def test_without_idempotency_key_each_post_creates_a_scan(auth_client: AsyncClient) -> None:
    site = await _authorized_site(auth_client, base_url="https://example.com")
    first = await auth_client.post(SCANS, json={"site_id": site["id"]})
    second = await auth_client.post(SCANS, json={"site_id": site["id"]})
    assert first.json()["id"] != second.json()["id"]


async def test_list_and_filter(auth_client: AsyncClient) -> None:
    site = await _authorized_site(auth_client, base_url="https://example.com")
    await auth_client.post(SCANS, json={"site_id": site["id"]})

    listing = (await auth_client.get(SCANS)).json()
    assert listing["total"] == 1
    assert listing["items"][0]["site_name"] == "Sitio"
    assert listing["items"][0]["site_base_url"] == "https://example.com"

    queued = (await auth_client.get(f"{SCANS}?status=queued")).json()
    assert queued["total"] == 1
    running = (await auth_client.get(f"{SCANS}?status=running")).json()
    assert running["total"] == 0


async def test_get_detail_includes_modules_and_scope(auth_client: AsyncClient) -> None:
    site = await _authorized_site(auth_client, base_url="https://example.com")
    created = await auth_client.post(SCANS, json={"site_id": site["id"]})

    response = await auth_client.get(f"{SCANS}/{created.json()['id']}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["modules"] == []
    assert body["scope_snapshot"]["base_url"] == "https://example.com"


async def test_pages_endpoint_is_empty_before_the_crawl(auth_client: AsyncClient) -> None:
    site = await _authorized_site(auth_client, base_url="https://example.com")
    created = await auth_client.post(SCANS, json={"site_id": site["id"]})
    response = await auth_client.get(f"{SCANS}/{created.json()['id']}/pages")
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_cancel_a_queued_scan(auth_client: AsyncClient) -> None:
    site = await _authorized_site(auth_client, base_url="https://example.com")
    created = await auth_client.post(SCANS, json={"site_id": site["id"]})
    scan_id = created.json()["id"]

    response = await auth_client.post(f"{SCANS}/{scan_id}/cancel")
    assert response.status_code == 202
    assert response.json()["status"] == ScanStatus.CANCELLED.value


async def test_cancelling_twice_returns_conflict(auth_client: AsyncClient) -> None:
    site = await _authorized_site(auth_client, base_url="https://example.com")
    created = await auth_client.post(SCANS, json={"site_id": site["id"]})
    scan_id = created.json()["id"]

    await auth_client.post(f"{SCANS}/{scan_id}/cancel")
    again = await auth_client.post(f"{SCANS}/{scan_id}/cancel")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "scan_already_finished"


@pytest.mark.security
async def test_scans_of_other_users_are_invisible(
    auth_client: AsyncClient,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    from softree_audit.models import Scan, ScanType

    _, session = app_context
    project = Project(owner_id=other_user.id, name="Ajeno")
    session.add(project)
    await session.flush()
    site = Site(project_id=project.id, name="Ajeno", base_url="https://ajeno.test")
    site.scope = Scope(allowed_domains=["ajeno.test"])
    session.add(site)
    await session.flush()
    scan = Scan(
        site_id=site.id,
        scan_type=ScanType.FULL,
        status=ScanStatus.QUEUED,
        scope_snapshot={"base_url": "https://ajeno.test", "allowed_domains": ["ajeno.test"]},
        engine_version="0.1.0",
        app_version="0.1.0",
    )
    session.add(scan)
    await session.commit()

    assert (await auth_client.get(SCANS)).json()["total"] == 0
    assert (await auth_client.get(f"{SCANS}/{scan.id}")).status_code == 404
    assert (await auth_client.get(f"{SCANS}/{scan.id}/pages")).status_code == 404
    assert (await auth_client.post(f"{SCANS}/{scan.id}/cancel")).status_code == 404


async def test_rate_limit_on_scan_creation(auth_client: AsyncClient) -> None:
    from softree_audit.core.rate_limit import SCAN_CREATE

    site = await _authorized_site(auth_client, base_url="https://example.com")
    for _ in range(SCAN_CREATE.max_requests):
        response = await auth_client.post(SCANS, json={"site_id": site["id"]})
        assert response.status_code == 202

    blocked = await auth_client.post(SCANS, json={"site_id": site["id"]})
    assert blocked.status_code == 429
