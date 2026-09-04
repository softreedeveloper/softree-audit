"""Generación y descarga de reportes."""

from __future__ import annotations

import datetime as dt
import json
import uuid

import pytest
from httpx import AsyncClient
from softree_audit.models import (
    Confidence,
    Finding,
    FindingCategory,
    FindingSource,
    ModuleName,
    ModuleStatus,
    Project,
    Scan,
    ScanModuleRun,
    ScanStatus,
    ScanType,
    Scope,
    SEOResult,
    Severity,
    Site,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

REPORTS = "/api/v1/reports"


async def _scan(
    session: AsyncSession, owner: User, *, status: ScanStatus = ScanStatus.COMPLETED
) -> Scan:
    project = Project(owner_id=owner.id, name=f"Proyecto {uuid.uuid4().hex[:6]}")
    session.add(project)
    await session.flush()

    site = Site(
        project_id=project.id,
        name="Sitio de prueba",
        base_url=f"https://sitio-{uuid.uuid4().hex[:6]}.test",
        authorized_by="Cliente",
        authorization_date=dt.date(2026, 1, 15),
    )
    site.scope = Scope(allowed_domains=["sitio.test"])
    session.add(site)
    await session.flush()

    scan = Scan(
        site_id=site.id,
        scan_type=ScanType.FULL,
        status=status,
        progress=100,
        started_at=dt.datetime.now(dt.UTC),
        finished_at=dt.datetime.now(dt.UTC),
        duration_ms=2000,
        scope_snapshot={"base_url": site.base_url},
        engine_version="0.1.0",
        app_version="0.1.0",
    )
    session.add(scan)
    await session.flush()

    session.add(
        ScanModuleRun(scan_id=scan.id, module=ModuleName.SEO, status=ModuleStatus.COMPLETED)
    )
    session.add(
        ScanModuleRun(
            scan_id=scan.id,
            module=ModuleName.PERFORMANCE,
            status=ModuleStatus.SKIPPED,
            detail={"reason": "quota_exceeded"},
        )
    )
    session.add(SEOResult(scan_id=scan.id, pages_crawled=18, urls_discovered=18, missing_title=1))
    session.add(
        Finding(
            scan_id=scan.id,
            source=FindingSource.SEO,
            category=FindingCategory.SEO,
            rule_id="SEO-001",
            title="Página sin elemento title",
            severity=Severity.HIGH,
            confidence=Confidence.HIGH,
            url=f"{site.base_url}/pagina",
            description="La página no declara un elemento title.",
            impact="Reduce la tasa de clic.",
            remediation="Añadir un title único.",
            client_explanation="Esta página no tiene título.",
            fingerprint=f"huella-{uuid.uuid4().hex}",
        )
    )
    await session.commit()
    return scan


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.post(f"{REPORTS}/{uuid.uuid4()}/generate")).status_code == 401


async def test_generates_the_three_formats(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    scan = await _scan(session, user)

    response = await auth_client.post(f"{REPORTS}/{scan.id}/generate")
    assert response.status_code == 201

    body = response.json()
    assert {item["format"] for item in body} == {"pdf", "html", "json"}
    for item in body:
        assert item["size_bytes"] > 0
        assert len(item["checksum_sha256"]) == 64
        assert item["report_version"] == "v1"


async def test_generates_only_the_requested_formats(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    scan = await _scan(session, user)

    body = (
        await auth_client.post(f"{REPORTS}/{scan.id}/generate", json={"formats": ["json"]})
    ).json()
    assert [item["format"] for item in body] == ["json"]


async def test_an_unfinished_scan_cannot_be_reported(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    scan = await _scan(session, user, status=ScanStatus.RUNNING)

    response = await auth_client.post(f"{REPORTS}/{scan.id}/generate")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "scan_not_finished"


async def test_a_partial_scan_can_be_reported(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """Una auditoría parcial sigue teniendo resultados que entregar."""
    _, session = app_context
    scan = await _scan(session, user, status=ScanStatus.PARTIAL)
    assert (await auth_client.post(f"{REPORTS}/{scan.id}/generate")).status_code == 201


async def test_downloads_the_pdf(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    scan = await _scan(session, user)
    await auth_client.post(f"{REPORTS}/{scan.id}/generate", json={"formats": ["pdf"]})

    response = await auth_client.get(f"{REPORTS}/{scan.id}/download?format=pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["x-report-version"] == "v1"
    # Un PDF real empieza con su firma.
    assert response.content.startswith(b"%PDF-")


async def test_downloads_the_json_with_the_full_model(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    scan = await _scan(session, user)
    await auth_client.post(f"{REPORTS}/{scan.id}/generate", json={"formats": ["json"]})

    response = await auth_client.get(f"{REPORTS}/{scan.id}/download?format=json")
    payload = json.loads(response.content)

    assert payload["scan_id"] == str(scan.id)
    assert payload["pages_crawled"] == 18
    assert any(section["key"] == "seo" for section in payload["sections"])
    assert "no constituye una calificación oficial de Google" in payload["methodology_disclaimer"]


async def test_the_report_declares_modules_that_did_not_run(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """No decirlo haría creer que la sección está limpia."""
    _, session = app_context
    scan = await _scan(session, user)
    await auth_client.post(f"{REPORTS}/{scan.id}/generate", json={"formats": ["json"]})

    payload = json.loads(
        (await auth_client.get(f"{REPORTS}/{scan.id}/download?format=json")).content
    )
    performance = next(s for s in payload["sections"] if s["key"] == "performance")
    assert performance["module_status"] == "skipped"
    assert "quota_exceeded" in performance["note"]


async def test_downloading_before_generating_returns_404(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    scan = await _scan(session, user)
    assert (await auth_client.get(f"{REPORTS}/{scan.id}/download")).status_code == 404


async def test_regenerating_replaces_the_previous_file(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """No se acumulan versiones idénticas del mismo reporte."""
    _, session = app_context
    scan = await _scan(session, user)

    first = (
        await auth_client.post(f"{REPORTS}/{scan.id}/generate", json={"formats": ["json"]})
    ).json()
    second = (
        await auth_client.post(f"{REPORTS}/{scan.id}/generate", json={"formats": ["json"]})
    ).json()

    assert first[0]["id"] == second[0]["id"]
    assert len((await auth_client.get(f"{REPORTS}/{scan.id}")).json()) == 1


async def test_listing_reports(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    scan = await _scan(session, user)
    await auth_client.post(f"{REPORTS}/{scan.id}/generate")

    body = (await auth_client.get(f"{REPORTS}/{scan.id}")).json()
    assert len(body) == 3


async def test_an_empty_format_list_is_rejected(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    scan = await _scan(session, user)
    response = await auth_client.post(f"{REPORTS}/{scan.id}/generate", json={"formats": []})
    assert response.status_code == 422


@pytest.mark.security
async def test_cannot_generate_a_report_of_another_users_scan(
    auth_client: AsyncClient, other_user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    scan = await _scan(session, other_user)

    assert (await auth_client.post(f"{REPORTS}/{scan.id}/generate")).status_code == 404
    assert (await auth_client.get(f"{REPORTS}/{scan.id}")).status_code == 404
    assert (await auth_client.get(f"{REPORTS}/{scan.id}/download")).status_code == 404


@pytest.mark.security
async def test_report_generation_is_rate_limited(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    from softree_audit.core.rate_limit import REPORT_GENERATE

    _, session = app_context
    scan = await _scan(session, user)

    for _ in range(REPORT_GENERATE.max_requests):
        response = await auth_client.post(
            f"{REPORTS}/{scan.id}/generate", json={"formats": ["json"]}
        )
        assert response.status_code == 201

    blocked = await auth_client.post(f"{REPORTS}/{scan.id}/generate", json={"formats": ["json"]})
    assert blocked.status_code == 429


# ── Audiencia ──────────────────────────────────────────────────────────────


async def test_each_audience_produces_its_own_pdf(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """La versión ejecutiva y la técnica son dos archivos, no uno sobrescrito."""
    _, session = app_context
    scan = await _scan(session, user)

    executive = await auth_client.post(
        f"{REPORTS}/{scan.id}/generate", json={"formats": ["pdf"], "audience": "executive"}
    )
    technical = await auth_client.post(
        f"{REPORTS}/{scan.id}/generate", json={"formats": ["pdf"], "audience": "technical"}
    )
    assert executive.status_code == 201
    assert technical.status_code == 201
    assert executive.json()[0]["id"] != technical.json()[0]["id"]

    reports = (await auth_client.get(f"{REPORTS}/{scan.id}")).json()
    paths = {report["audience"] for report in reports}
    assert paths == {"executive", "technical"}

    first = await auth_client.get(f"{REPORTS}/{scan.id}/download?format=pdf&audience=executive")
    second = await auth_client.get(f"{REPORTS}/{scan.id}/download?format=pdf&audience=technical")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers["x-report-audience"] == "executive"
    assert second.headers["x-report-audience"] == "technical"
    assert "executive" in first.headers["content-disposition"]
    # Dos documentos distintos: si compartieran archivo, serían idénticos.
    assert first.content != second.content
    assert first.content.startswith(b"%PDF-")
    assert second.content.startswith(b"%PDF-")


async def test_downloading_without_audience_returns_the_most_recent(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """Quien solo quiere «el PDF» no tiene que saber de audiencias."""
    _, session = app_context
    scan = await _scan(session, user)

    await auth_client.post(
        f"{REPORTS}/{scan.id}/generate", json={"formats": ["pdf"], "audience": "executive"}
    )
    response = await auth_client.get(f"{REPORTS}/{scan.id}/download?format=pdf")

    assert response.status_code == 200
    assert response.headers["x-report-audience"] == "executive"


async def test_an_audience_that_was_not_generated_returns_404(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    scan = await _scan(session, user)
    await auth_client.post(
        f"{REPORTS}/{scan.id}/generate", json={"formats": ["pdf"], "audience": "executive"}
    )

    response = await auth_client.get(f"{REPORTS}/{scan.id}/download?format=pdf&audience=technical")
    assert response.status_code == 404
