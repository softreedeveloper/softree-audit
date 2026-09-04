"""Dashboard, histórico y comparación."""

from __future__ import annotations

import datetime as dt
import decimal
import uuid

import pytest
from httpx import AsyncClient
from softree_audit.models import (
    Confidence,
    Finding,
    FindingCategory,
    FindingSource,
    FindingStatus,
    ModuleName,
    ModuleStatus,
    Project,
    Scan,
    ScanModuleRun,
    ScanStatus,
    ScanType,
    Scope,
    Score,
    ScoreCategory,
    ScoreSystem,
    SEOResult,
    Severity,
    Site,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

DASHBOARD = "/api/v1/dashboard"
SITES = "/api/v1/sites"
SCANS = "/api/v1/scans"


async def _site(session: AsyncSession, owner: User, *, authorized: bool = True) -> Site:
    project = Project(owner_id=owner.id, name=f"Proyecto {uuid.uuid4().hex[:6]}")
    session.add(project)
    await session.flush()

    site = Site(
        project_id=project.id,
        name="Sitio",
        base_url=f"https://sitio-{uuid.uuid4().hex[:6]}.test",
        authorized_by="Cliente" if authorized else None,
        authorization_date=dt.date(2026, 1, 15) if authorized else None,
    )
    site.scope = Scope(allowed_domains=["sitio.test"])
    session.add(site)
    await session.flush()
    return site


async def _scan(
    session: AsyncSession,
    site: Site,
    *,
    status: ScanStatus = ScanStatus.COMPLETED,
    score: float | None = None,
    findings: list[tuple[str, Severity]] | None = None,
    seo: dict[str, int] | None = None,
    modules: tuple[ModuleName, ...] = (ModuleName.CRAWLER, ModuleName.SEO),
) -> Scan:
    scan = Scan(
        site_id=site.id,
        scan_type=ScanType.FULL,
        status=status,
        progress=100,
        finished_at=dt.datetime.now(dt.UTC),
        duration_ms=1500,
        scope_snapshot={"base_url": site.base_url},
        engine_version="0.1.0",
        app_version="0.1.0",
    )
    session.add(scan)
    await session.flush()

    # Un scan terminado siempre tiene filas de módulo: la comparación las usa
    # para saber qué fuentes midió cada auditoría.
    for module in modules:
        session.add(ScanModuleRun(scan_id=scan.id, module=module, status=ModuleStatus.COMPLETED))

    if score is not None:
        session.add(
            Score(
                scan_id=scan.id,
                system=ScoreSystem.SOFTREE,
                category=ScoreCategory.OVERALL,
                value=decimal.Decimal(str(score)),
                detail={"band": "bueno"},
                engine_version="0.1.0",
            )
        )

    for fingerprint, severity in findings or []:
        session.add(
            Finding(
                scan_id=scan.id,
                source=FindingSource.SEO,
                category=FindingCategory.SEO,
                rule_id="SEO-001",
                title=f"Hallazgo {fingerprint}",
                severity=severity,
                confidence=Confidence.HIGH,
                description="Descripción",
                fingerprint=fingerprint,
            )
        )

    if seo is not None:
        session.add(SEOResult(scan_id=scan.id, **seo))

    await session.flush()
    return scan


# ── Dashboard ──────────────────────────────────────────────────────────────


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(DASHBOARD)).status_code == 401


async def test_empty_dashboard(auth_client: AsyncClient) -> None:
    body = (await auth_client.get(DASHBOARD)).json()
    assert body["projects"] == 0
    assert body["sites"] == 0
    assert body["average_score"] is None
    assert body["recent_scans"] == []


async def test_dashboard_counts_projects_sites_and_scans(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    site = await _site(session, user)
    await _site(session, user, authorized=False)
    await _scan(session, site, score=86.7)
    await session.commit()

    body = (await auth_client.get(DASHBOARD)).json()
    assert body["projects"] == 2
    assert body["sites"] == 2
    assert body["authorized_sites"] == 1
    assert body["scans"] == 1
    assert body["average_score"] == 86.7
    assert len(body["recent_scans"]) == 1


async def test_dashboard_only_counts_the_latest_scan_of_each_site(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """Sumar todos los scans multiplicaría los hallazgos por auditoría."""
    _, session = app_context
    site = await _site(session, user)
    await _scan(session, site, findings=[("viejo-1", Severity.HIGH), ("viejo-2", Severity.HIGH)])
    await _scan(session, site, findings=[("nuevo-1", Severity.HIGH)])
    await session.commit()

    body = (await auth_client.get(DASHBOARD)).json()
    assert body["open_findings_by_severity"]["high"] == 1


async def test_dashboard_ignores_resolved_findings(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    import sqlalchemy as sa

    _, session = app_context
    site = await _site(session, user)
    scan = await _scan(session, site, findings=[("a", Severity.HIGH), ("b", Severity.HIGH)])
    await session.execute(
        sa.update(Finding)
        .where(Finding.scan_id == scan.id, Finding.fingerprint == "a")
        .values(status=FindingStatus.FIXED)
    )
    await session.commit()

    body = (await auth_client.get(DASHBOARD)).json()
    assert body["open_findings_by_severity"]["high"] == 1


async def test_dashboard_reports_scans_in_progress(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    site = await _site(session, user)
    await _scan(session, site, status=ScanStatus.RUNNING)
    await session.commit()

    assert (await auth_client.get(DASHBOARD)).json()["scans_in_progress"] == 1


@pytest.mark.security
async def test_dashboard_only_shows_data_of_the_current_user(
    auth_client: AsyncClient,
    user: User,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    _, session = app_context
    mine = await _site(session, user)
    theirs = await _site(session, other_user)
    await _scan(session, mine, score=90.0)
    await _scan(session, theirs, score=10.0, findings=[("ajeno", Severity.CRITICAL)])
    await session.commit()

    body = (await auth_client.get(DASHBOARD)).json()
    assert body["sites"] == 1
    assert body["average_score"] == 90.0
    assert body["open_findings_by_severity"]["critical"] == 0


# ── Histórico ──────────────────────────────────────────────────────────────


async def test_history_lists_scans_newest_first(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    site = await _site(session, user)
    first = await _scan(session, site, score=60.0)
    second = await _scan(session, site, score=80.0)
    await session.commit()

    body = (await auth_client.get(f"{SITES}/{site.id}/history")).json()
    assert [entry["scan_id"] for entry in body] == [str(second.id), str(first.id)]
    assert body[0]["softree_overall"] == 80.0


async def test_history_includes_open_finding_counts(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    site = await _site(session, user)
    await _scan(session, site, findings=[("a", Severity.HIGH), ("b", Severity.LOW)])
    await session.commit()

    body = (await auth_client.get(f"{SITES}/{site.id}/history")).json()
    assert body[0]["open_findings"] == 2


@pytest.mark.security
async def test_history_of_another_users_site_returns_404(
    auth_client: AsyncClient, other_user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    site = await _site(session, other_user)
    await session.commit()
    assert (await auth_client.get(f"{SITES}/{site.id}/history")).status_code == 404


# ── Comparación ────────────────────────────────────────────────────────────


async def test_comparison_between_two_scans(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    site = await _site(session, user)
    await _scan(
        session,
        site,
        score=60.0,
        findings=[("igual", Severity.MEDIUM), ("resuelto", Severity.HIGH)],
        seo={"pages_crawled": 10, "broken_internal_links": 12, "missing_title": 7},
    )
    current = await _scan(
        session,
        site,
        score=86.0,
        findings=[("igual", Severity.MEDIUM), ("nuevo", Severity.LOW)],
        seo={"pages_crawled": 10, "broken_internal_links": 3, "missing_title": 2},
    )
    await session.commit()

    body = (await auth_client.get(f"{SCANS}/{current.id}/comparison")).json()

    assert body["counts"] == {"new": 1, "fixed": 1, "unchanged": 1, "regressed": 0}
    assert body["compared_sources"] == ["crawler", "seo"]

    metrics = {item["key"]: item for item in body["metrics"]}
    # El ejemplo de la especificación: 12 → 3 y 7 → 2.
    assert metrics["broken_internal_links"]["previous"] == 12.0
    assert metrics["broken_internal_links"]["current"] == 3.0
    assert metrics["broken_internal_links"]["direction"] == "mejora"
    assert metrics["missing_title"]["delta"] == -5.0
    assert metrics["softree_overall"]["direction"] == "mejora"


async def test_comparison_without_a_previous_scan_returns_409(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    site = await _site(session, user)
    scan = await _scan(session, site)
    await session.commit()

    response = await auth_client.get(f"{SCANS}/{scan.id}/comparison")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_previous_scan"


async def test_comparison_against_a_specific_scan(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    site = await _site(session, user)
    oldest = await _scan(session, site, score=40.0)
    await _scan(session, site, score=60.0)
    current = await _scan(session, site, score=86.0)
    await session.commit()

    body = (await auth_client.get(f"{SCANS}/{current.id}/comparison?against={oldest.id}")).json()
    assert body["previous"]["scan_id"] == str(oldest.id)
    metrics = {item["key"]: item for item in body["metrics"]}
    assert metrics["softree_overall"]["previous"] == 40.0


@pytest.mark.security
async def test_cannot_compare_scans_of_different_sites(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """Comparar sitios distintos no significaría nada."""
    _, session = app_context
    first = await _site(session, user)
    second = await _site(session, user)
    a = await _scan(session, first)
    b = await _scan(session, second)
    await session.commit()

    response = await auth_client.get(f"{SCANS}/{a.id}/comparison?against={b.id}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "different_site"


@pytest.mark.security
async def test_cannot_compare_against_another_users_scan(
    auth_client: AsyncClient,
    user: User,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    _, session = app_context
    mine = await _site(session, user)
    theirs = await _site(session, other_user)
    a = await _scan(session, mine)
    await _scan(session, mine)
    b = await _scan(session, theirs)
    await session.commit()

    assert (await auth_client.get(f"{SCANS}/{a.id}/comparison?against={b.id}")).status_code == 404


@pytest.mark.security
async def test_a_module_that_did_not_run_is_not_reported_as_fixed(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """Comparar un scan SEO con uno completo no debe «corregir» lo de seguridad."""
    _, session = app_context
    site = await _site(session, user)

    full = await _scan(
        session,
        site,
        modules=(ModuleName.CRAWLER, ModuleName.SEO, ModuleName.SECURITY),
        findings=[("seo-1", Severity.MEDIUM)],
    )
    session.add(
        Finding(
            scan_id=full.id,
            source=FindingSource.ZAP,
            category=FindingCategory.SECURITY,
            rule_id="10038-1",
            title="CSP ausente",
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH,
            description="Descripción",
            fingerprint="zap-1",
        )
    )
    only_seo = await _scan(
        session,
        site,
        modules=(ModuleName.CRAWLER, ModuleName.SEO),
        findings=[("seo-1", Severity.MEDIUM)],
    )
    await session.commit()

    body = (await auth_client.get(f"{SCANS}/{only_seo.id}/comparison")).json()

    assert body["counts"]["fixed"] == 0
    assert body["compared_sources"] == ["crawler", "seo"]
    assert body["sources_only_in_previous"] == ["zap"]


async def test_dashboard_reports_the_score_by_category(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """La portada necesita el desglose, no solo el score global."""
    _, session = app_context
    site = await _site(session, user)
    scan = await _scan(session, site, status=ScanStatus.COMPLETED)
    session.add_all(
        [
            Score(
                scan_id=scan.id,
                system=ScoreSystem.SOFTREE,
                category=ScoreCategory.SEO,
                value=decimal.Decimal("91.7"),
                engine_version="0.1.0",
            ),
            Score(
                scan_id=scan.id,
                system=ScoreSystem.SOFTREE,
                category=ScoreCategory.SECURITY,
                value=decimal.Decimal("83.2"),
                engine_version="0.1.0",
            ),
        ]
    )
    await session.commit()

    body = (await auth_client.get(DASHBOARD)).json()

    assert body["score_by_category"]["seo"] == 91.7
    assert body["score_by_category"]["security"] == 83.2
    # Una categoría que ningún sitio midió es `null`, nunca cero.
    assert body["score_by_category"]["accessibility"] is None


async def test_dashboard_reports_the_score_trend_in_order(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    site = await _site(session, user)

    for index, value in enumerate(("70.0", "80.0", "90.0")):
        scan = await _scan(session, site, status=ScanStatus.COMPLETED)
        scan.finished_at = dt.datetime(2026, 9, 1 + index, 12, 0, tzinfo=dt.UTC)
        session.add(
            Score(
                scan_id=scan.id,
                system=ScoreSystem.SOFTREE,
                category=ScoreCategory.OVERALL,
                value=decimal.Decimal(value),
                engine_version="0.1.0",
            )
        )
    await session.commit()

    trend = (await auth_client.get(DASHBOARD)).json()["score_trend"]

    # Orden cronológico: el gráfico se dibuja de izquierda a derecha.
    assert [point["score"] for point in trend] == [70.0, 80.0, 90.0]
    assert trend[0]["site_name"] == site.name


@pytest.mark.security
async def test_the_trend_only_contains_your_own_audits(
    auth_client: AsyncClient,
    user: User,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    _, session = app_context
    foreign_site = await _site(session, other_user)
    foreign = await _scan(session, foreign_site, status=ScanStatus.COMPLETED)
    foreign.finished_at = dt.datetime(2026, 9, 2, 12, 0, tzinfo=dt.UTC)
    session.add(
        Score(
            scan_id=foreign.id,
            system=ScoreSystem.SOFTREE,
            category=ScoreCategory.OVERALL,
            value=decimal.Decimal("42.0"),
            engine_version="0.1.0",
        )
    )
    await session.commit()

    body = (await auth_client.get(DASHBOARD)).json()

    assert body["score_trend"] == []
    assert all(value is None for value in body["score_by_category"].values())
