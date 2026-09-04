"""Endpoints de hallazgos y resumen SEO por sitio."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from httpx import AsyncClient
from softree_audit.models import (
    Confidence,
    Finding,
    FindingCategory,
    FindingSource,
    FindingStatus,
    Project,
    Scan,
    ScanStatus,
    ScanType,
    Scope,
    SEOResult,
    Severity,
    Site,
    User,
)
from softree_audit.services.findings.models import build_fingerprint
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

FINDINGS = "/api/v1/findings"
SCANS = "/api/v1/scans"
SITES = "/api/v1/sites"


async def _seed(
    session: AsyncSession,
    owner: User,
    *,
    severities: list[Severity] | None = None,
    with_seo_result: bool = True,
) -> tuple[Site, Scan]:
    project = Project(owner_id=owner.id, name=f"Proyecto {uuid.uuid4().hex[:6]}")
    session.add(project)
    await session.flush()

    site = Site(
        project_id=project.id,
        name="Sitio",
        base_url=f"https://sitio-{uuid.uuid4().hex[:6]}.test",
        authorized_by="Cliente",
        authorization_date=dt.date(2026, 1, 15),
    )
    site.scope = Scope(allowed_domains=["sitio.test"])
    session.add(site)
    await session.flush()

    scan = Scan(
        site_id=site.id,
        scan_type=ScanType.SEO,
        status=ScanStatus.COMPLETED,
        progress=100,
        finished_at=dt.datetime.now(dt.UTC),
        scope_snapshot={"base_url": site.base_url, "allowed_domains": ["sitio.test"]},
        engine_version="0.1.0",
        app_version="0.1.0",
    )
    session.add(scan)
    await session.flush()

    for index, severity in enumerate(severities or [Severity.HIGH, Severity.LOW]):
        rule = f"SEO-{index + 1:03d}"
        url = f"{site.base_url}/pagina-{index}"
        session.add(
            Finding(
                scan_id=scan.id,
                source=FindingSource.SEO,
                category=FindingCategory.SEO,
                rule_id=rule,
                title=f"Hallazgo {rule}",
                severity=severity,
                confidence=Confidence.HIGH,
                url=url,
                description="Descripción",
                fingerprint=build_fingerprint(
                    source=FindingSource.SEO,
                    rule_id=rule,
                    category=FindingCategory.SEO,
                    url=url,
                    parameter=None,
                ),
            )
        )

    if with_seo_result:
        session.add(
            SEOResult(
                scan_id=scan.id,
                pages_crawled=10,
                urls_discovered=12,
                missing_title=1,
                sitemap_found=True,
                robots_txt_found=True,
            )
        )

    await session.commit()
    return site, scan


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(FINDINGS)).status_code == 401


async def test_list_findings(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    await _seed(session, user)

    response = await auth_client.get(FINDINGS)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["source"] == "seo"


async def test_findings_are_ordered_by_severity(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """Lo más grave primero: es lo que hay que atender antes."""
    _, session = app_context
    await _seed(session, user, severities=[Severity.LOW, Severity.CRITICAL, Severity.MEDIUM])

    items = (await auth_client.get(FINDINGS)).json()["items"]
    assert [item["severity"] for item in items] == ["critical", "medium", "low"]


async def test_filter_by_severity_and_source(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    await _seed(session, user, severities=[Severity.HIGH, Severity.LOW])

    high = (await auth_client.get(f"{FINDINGS}?severity=high")).json()
    assert high["total"] == 1

    zap = (await auth_client.get(f"{FINDINGS}?source=zap")).json()
    assert zap["total"] == 0


async def test_filter_by_scan_and_site(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    site, scan = await _seed(session, user)

    by_scan = (await auth_client.get(f"{FINDINGS}?scan_id={scan.id}")).json()
    assert by_scan["total"] == 2

    by_site = (await auth_client.get(f"{FINDINGS}?site_id={site.id}")).json()
    assert by_site["total"] == 2


async def test_scan_findings_endpoint(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    _, scan = await _seed(session, user)

    response = await auth_client.get(f"{SCANS}/{scan.id}/findings")
    assert response.status_code == 200
    assert response.json()["total"] == 2


async def test_severity_counts_endpoint(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    _, scan = await _seed(
        session, user, severities=[Severity.CRITICAL, Severity.HIGH, Severity.HIGH]
    )

    counts = (await auth_client.get(f"{SCANS}/{scan.id}/severity-counts")).json()
    assert counts["critical"] == 1
    assert counts["high"] == 2
    assert counts["low"] == 0


async def test_status_can_be_changed(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    await _seed(session, user)
    finding_id = (await auth_client.get(FINDINGS)).json()["items"][0]["id"]

    response = await auth_client.patch(
        f"{FINDINGS}/{finding_id}", json={"status": "false_positive"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "false_positive"


async def test_findings_marked_as_resolved_stop_counting(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """`docs/spec/scoring.md` §3: solo los abiertos penalizan."""
    _, session = app_context
    _, scan = await _seed(session, user, severities=[Severity.HIGH, Severity.HIGH])
    finding_id = (await auth_client.get(FINDINGS)).json()["items"][0]["id"]

    await auth_client.patch(f"{FINDINGS}/{finding_id}", json={"status": "fixed"})

    counts = (await auth_client.get(f"{SCANS}/{scan.id}/severity-counts")).json()
    assert counts["high"] == 1

    still_listed = (await auth_client.get(f"{FINDINGS}?status={FindingStatus.FIXED.value}")).json()
    assert still_listed["total"] == 1


async def test_invalid_status_is_rejected(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    await _seed(session, user)
    finding_id = (await auth_client.get(FINDINGS)).json()["items"][0]["id"]

    response = await auth_client.patch(f"{FINDINGS}/{finding_id}", json={"status": "inventado"})
    assert response.status_code == 422


@pytest.mark.security
async def test_findings_of_other_users_are_invisible(
    auth_client: AsyncClient,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    _, session = app_context
    _, scan = await _seed(session, other_user)

    assert (await auth_client.get(FINDINGS)).json()["total"] == 0
    assert (await auth_client.get(f"{SCANS}/{scan.id}/findings")).status_code == 404

    foreign_id = (
        await session.execute(__import__("sqlalchemy").select(Finding.id).limit(1))
    ).scalar_one()
    assert (
        await auth_client.patch(f"{FINDINGS}/{foreign_id}", json={"status": "fixed"})
    ).status_code == 404


# ── Resumen SEO del sitio ──────────────────────────────────────────────────


async def test_site_seo_summary(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    site, scan = await _seed(session, user, severities=[Severity.HIGH, Severity.MEDIUM])

    response = await auth_client.get(f"{SITES}/{site.id}/seo")
    assert response.status_code == 200
    body = response.json()
    assert body["scan_id"] == str(scan.id)
    assert body["result"]["pages_crawled"] == 10
    assert body["findings_by_severity"]["high"] == 1
    assert len(body["top_rules"]) == 2


async def test_site_without_finished_scans_returns_404(auth_client: AsyncClient) -> None:
    project = await auth_client.post("/api/v1/projects", json={"name": "Vacío"})
    site = await auth_client.post(
        SITES,
        json={
            "project_id": project.json()["id"],
            "name": "Sin auditar",
            "base_url": "https://sin-auditar.test",
        },
    )
    response = await auth_client.get(f"{SITES}/{site.json()['id']}/seo")
    assert response.status_code == 404


@pytest.mark.security
async def test_seo_summary_of_another_users_site_is_not_reachable(
    auth_client: AsyncClient,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    _, session = app_context
    site, _ = await _seed(session, other_user)
    assert (await auth_client.get(f"{SITES}/{site.id}/seo")).status_code == 404


# ── Resumen de seguridad del sitio ─────────────────────────────────────────


async def test_site_security_summary_reports_the_module_status(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """Si el módulo no se ejecutó hay que decirlo, no dar el sitio por limpio."""
    _, session = app_context
    site, _ = await _seed(session, user)

    response = await auth_client.get(f"{SITES}/{site.id}/security")
    assert response.status_code == 200
    assert response.json()["module_status"] == "no_ejecutado"


async def test_site_security_summary_with_zap_findings(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    from softree_audit.models import ModuleName, ModuleStatus, ScanModuleRun

    _, session = app_context
    site, scan = await _seed(session, user)

    session.add(
        ScanModuleRun(
            scan_id=scan.id,
            module=ModuleName.SECURITY,
            status=ModuleStatus.COMPLETED,
            detail={"alerts_received": 83, "findings": 2, "active_scan": False},
        )
    )
    for index, severity in enumerate([Severity.MEDIUM, Severity.LOW]):
        session.add(
            Finding(
                scan_id=scan.id,
                source=FindingSource.ZAP,
                category=FindingCategory.SECURITY,
                rule_id=f"1003{index}-1",
                title=f"Alerta {index}",
                severity=severity,
                confidence=Confidence.HIGH,
                description="Descripción",
                cwe="CWE-693",
                owasp="OWASP 2021 A05",
                occurrences=19 - index,
                fingerprint=build_fingerprint(
                    source=FindingSource.ZAP,
                    rule_id=f"1003{index}-1",
                    category=FindingCategory.SECURITY,
                    url=None,
                    parameter=None,
                ),
            )
        )
    await session.commit()

    body = (await auth_client.get(f"{SITES}/{site.id}/security")).json()
    assert body["module_status"] == "completed"
    assert body["module_detail"]["active_scan"] is False
    # El recuento suma los hallazgos SEO del fixture y los de ZAP: es un
    # recuento por scan, no por fuente.
    assert body["findings_by_severity"]["medium"] == 1
    assert body["findings_by_severity"]["low"] == 2
    # `top_findings` sí se limita a ZAP, con lo más grave primero.
    assert body["top_findings"][0]["severity"] == "medium"
    assert body["top_findings"][0]["cwe"] == "CWE-693"


@pytest.mark.security
async def test_security_summary_of_another_users_site_is_not_reachable(
    auth_client: AsyncClient,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    _, session = app_context
    site, _ = await _seed(session, other_user)
    assert (await auth_client.get(f"{SITES}/{site.id}/security")).status_code == 404


async def test_findings_can_be_filtered_by_security_category(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    _, scan = await _seed(session, user)
    session.add(
        Finding(
            scan_id=scan.id,
            source=FindingSource.ZAP,
            category=FindingCategory.SECURITY,
            rule_id="10038-1",
            title="CSP ausente",
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH,
            description="Descripción",
            fingerprint="huella-seguridad-unica",
        )
    )
    await session.commit()

    security_only = (await auth_client.get(f"{FINDINGS}?category=security")).json()
    assert security_only["total"] == 1
    assert security_only["items"][0]["source"] == "zap"


# ── Resumen de rendimiento del sitio ───────────────────────────────────────


async def test_site_performance_summary(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    import decimal

    from softree_audit.models import (
        ModuleName,
        ModuleStatus,
        PageSpeedStrategy,
        PerformanceResult,
        ScanModuleRun,
        Score,
        ScoreCategory,
        ScoreSystem,
    )

    _, session = app_context
    site, scan = await _seed(session, user)

    session.add(
        ScanModuleRun(
            scan_id=scan.id,
            module=ModuleName.PERFORMANCE,
            status=ModuleStatus.COMPLETED,
            detail={"strategies_analyzed": ["mobile", "desktop"], "has_field_data": False},
        )
    )
    for strategy, score, lcp in (
        (PageSpeedStrategy.MOBILE, 62, 3800),
        (PageSpeedStrategy.DESKTOP, 91, 1400),
    ):
        session.add(
            PerformanceResult(
                scan_id=scan.id,
                url=site.base_url,
                strategy=strategy,
                performance_score=score,
                accessibility_score=88,
                lcp_ms=lcp,
                cls=decimal.Decimal("0.0430"),
                # Sin datos de campo, INP debe quedar nulo, nunca cero (R4).
                inp_ms=None,
                has_field_data=False,
                lighthouse_version="12.2.1",
                raw={"lighthouseResult": {"lighthouseVersion": "12.2.1"}},
            )
        )
    session.add(
        Score(
            scan_id=scan.id,
            system=ScoreSystem.GOOGLE,
            category=ScoreCategory.PERFORMANCE,
            value=decimal.Decimal("62"),
            detail={"by_strategy": {"mobile": 62, "desktop": 91}, "primary": "mobile"},
            engine_version="0.1.0",
        )
    )
    await session.commit()

    body = (await auth_client.get(f"{SITES}/{site.id}/performance")).json()
    assert body["module_status"] == "completed"
    assert len(body["results"]) == 2

    by_strategy = {row["strategy"]: row for row in body["results"]}
    assert by_strategy["mobile"]["performance_score"] == 62
    assert by_strategy["desktop"]["performance_score"] == 91
    assert by_strategy["mobile"]["inp_ms"] is None
    assert by_strategy["mobile"]["has_field_data"] is False

    # El Google Score se devuelve sin transformar y con su desglose.
    assert body["google_scores"][0]["category"] == "performance"
    assert float(body["google_scores"][0]["value"]) == 62.0
    assert body["google_scores"][0]["detail"]["by_strategy"]["desktop"] == 91


async def test_performance_summary_reports_when_the_module_did_not_run(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    site, _ = await _seed(session, user)
    body = (await auth_client.get(f"{SITES}/{site.id}/performance")).json()
    assert body["module_status"] == "no_ejecutado"
    assert body["results"] == []


@pytest.mark.security
async def test_performance_summary_of_another_users_site_is_not_reachable(
    auth_client: AsyncClient,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    _, session = app_context
    site, _ = await _seed(session, other_user)
    assert (await auth_client.get(f"{SITES}/{site.id}/performance")).status_code == 404
