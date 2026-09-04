"""Puntuaciones del scan y arrastre de estados entre auditorías."""

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
    Project,
    Scan,
    ScanStatus,
    ScanType,
    Scope,
    Score,
    ScoreCategory,
    ScoreSystem,
    Severity,
    Site,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

SCANS = "/api/v1/scans"


async def _site_with_scan(
    session: AsyncSession, owner: User, *, status: ScanStatus = ScanStatus.COMPLETED
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
        scan_type=ScanType.FULL,
        status=status,
        progress=100,
        finished_at=dt.datetime.now(dt.UTC),
        scope_snapshot={"base_url": site.base_url},
        engine_version="0.1.0",
        app_version="0.1.0",
    )
    session.add(scan)
    await session.flush()
    return site, scan


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(f"{SCANS}/{uuid.uuid4()}/scores")).status_code == 401


async def test_scores_are_returned_separated_by_system(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """§27: nunca se presenta el cálculo propio como si fuera de Google."""
    _, session = app_context
    _, scan = await _site_with_scan(session, user)

    session.add_all(
        [
            Score(
                scan_id=scan.id,
                system=ScoreSystem.GOOGLE,
                category=ScoreCategory.PERFORMANCE,
                value=decimal.Decimal("62"),
                detail={"by_strategy": {"mobile": 62}},
                engine_version="0.1.0",
            ),
            Score(
                scan_id=scan.id,
                system=ScoreSystem.SOFTREE,
                category=ScoreCategory.SECURITY,
                value=decimal.Decimal("83.2"),
                weight=decimal.Decimal("0.5455"),
                detail={"total_penalty": 16.8},
                engine_version="0.1.0",
            ),
            Score(
                scan_id=scan.id,
                system=ScoreSystem.SOFTREE,
                category=ScoreCategory.OVERALL,
                value=decimal.Decimal("86.7"),
                detail={"band": "bueno"},
                engine_version="0.1.0",
            ),
        ]
    )
    await session.commit()

    body = (await auth_client.get(f"{SCANS}/{scan.id}/scores")).json()

    assert float(body["softree_overall"]) == 86.7
    assert body["band"] == "bueno"
    assert [item["category"] for item in body["google"]] == ["performance"]
    assert {item["category"] for item in body["softree"]} == {"security", "overall"}
    assert "no constituye una calificación oficial de Google" in body["disclaimer"]


async def test_applied_weights_are_persisted_with_the_score(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """Un cambio de configuración no debe alterar los scans históricos."""
    _, session = app_context
    _, scan = await _site_with_scan(session, user)
    session.add(
        Score(
            scan_id=scan.id,
            system=ScoreSystem.SOFTREE,
            category=ScoreCategory.SEO,
            value=decimal.Decimal("90.8"),
            weight=decimal.Decimal("0.4545"),
            detail={},
            engine_version="0.1.0",
        )
    )
    await session.commit()

    body = (await auth_client.get(f"{SCANS}/{scan.id}/scores")).json()
    seo = next(item for item in body["softree"] if item["category"] == "seo")
    assert float(seo["weight"]) == 0.4545
    assert seo["engine_version"] == "0.1.0"


async def test_a_scan_without_scores_reports_nothing_rather_than_zero(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    _, session = app_context
    _, scan = await _site_with_scan(session, user)
    await session.commit()

    body = (await auth_client.get(f"{SCANS}/{scan.id}/scores")).json()
    assert body["softree_overall"] is None
    assert body["band"] is None
    assert body["softree"] == []


@pytest.mark.security
async def test_scores_of_another_user_are_not_reachable(
    auth_client: AsyncClient,
    other_user: User,
    app_context: tuple[object, AsyncSession],
) -> None:
    _, session = app_context
    _, scan = await _site_with_scan(session, other_user)
    await session.commit()
    assert (await auth_client.get(f"{SCANS}/{scan.id}/scores")).status_code == 404


# ── Arrastre de estados entre scans ────────────────────────────────────────


async def test_accepted_findings_carry_over_to_the_next_scan(
    app_context: tuple[object, AsyncSession], user: User, settings: object
) -> None:
    """Una decisión humana no debe repetirse en cada auditoría (§25)."""
    from softree_audit.models.enums import ModuleName
    from softree_audit.scans.orchestrator import ScanOrchestrator
    from softree_audit.services.findings.models import NormalizedFinding

    app, session = app_context
    site, first_scan = await _site_with_scan(session, user)

    finding = NormalizedFinding(
        source=FindingSource.ZAP,
        category=FindingCategory.SECURITY,
        rule_id="10038-1",
        title="CSP ausente",
        severity=Severity.MEDIUM,
        confidence=Confidence.HIGH,
        description="Descripción",
        url=f"{site.base_url}/",
    )

    session.add(
        Finding(
            scan_id=first_scan.id,
            source=finding.source,
            category=finding.category,
            rule_id=finding.rule_id,
            title=finding.title,
            severity=finding.severity,
            confidence=finding.confidence,
            url=finding.url,
            description=finding.description,
            fingerprint=finding.fingerprint,
            status=FindingStatus.ACCEPTED,
        )
    )

    second_scan = Scan(
        site_id=site.id,
        scan_type=ScanType.FULL,
        status=ScanStatus.RUNNING,
        scope_snapshot={"base_url": site.base_url},
        engine_version="0.1.0",
        app_version="0.1.0",
    )
    session.add(second_scan)
    await session.commit()

    orchestrator = ScanOrchestrator(
        app.state.session_factory,  # type: ignore[attr-defined]
        app.state.redis,  # type: ignore[attr-defined]
        settings,  # type: ignore[arg-type]
    )
    await orchestrator._persist_findings(second_scan.id, [finding])

    import sqlalchemy as sa

    status = await session.scalar(
        sa.select(Finding.status).where(
            Finding.scan_id == second_scan.id, Finding.fingerprint == finding.fingerprint
        )
    )
    assert status is FindingStatus.ACCEPTED
    assert ModuleName.SECURITY  # el módulo existe en el registro


async def test_fixed_findings_do_not_carry_over(
    app_context: tuple[object, AsyncSession], user: User, settings: object
) -> None:
    """Si el problema vuelve a detectarse es que no está corregido."""
    import sqlalchemy as sa
    from softree_audit.scans.orchestrator import ScanOrchestrator
    from softree_audit.services.findings.models import NormalizedFinding

    app, session = app_context
    site, first_scan = await _site_with_scan(session, user)

    finding = NormalizedFinding(
        source=FindingSource.SEO,
        category=FindingCategory.SEO,
        rule_id="SEO-001",
        title="Sin title",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        description="Descripción",
        url=f"{site.base_url}/pagina",
    )
    session.add(
        Finding(
            scan_id=first_scan.id,
            source=finding.source,
            category=finding.category,
            rule_id=finding.rule_id,
            title=finding.title,
            severity=finding.severity,
            confidence=finding.confidence,
            url=finding.url,
            description=finding.description,
            fingerprint=finding.fingerprint,
            status=FindingStatus.FIXED,
        )
    )
    second_scan = Scan(
        site_id=site.id,
        scan_type=ScanType.SEO,
        status=ScanStatus.RUNNING,
        scope_snapshot={"base_url": site.base_url},
        engine_version="0.1.0",
        app_version="0.1.0",
    )
    session.add(second_scan)
    await session.commit()

    orchestrator = ScanOrchestrator(
        app.state.session_factory,  # type: ignore[attr-defined]
        app.state.redis,  # type: ignore[attr-defined]
        settings,  # type: ignore[arg-type]
    )
    await orchestrator._persist_findings(second_scan.id, [finding])

    status = await session.scalar(
        sa.select(Finding.status).where(Finding.scan_id == second_scan.id)
    )
    assert status is FindingStatus.OPEN


@pytest.mark.security
async def test_statuses_do_not_carry_over_between_sites(
    app_context: tuple[object, AsyncSession], user: User, settings: object
) -> None:
    """Aceptar un hallazgo en un sitio no debe silenciarlo en otro."""
    import sqlalchemy as sa
    from softree_audit.scans.orchestrator import ScanOrchestrator
    from softree_audit.services.findings.models import NormalizedFinding

    app, session = app_context
    _, other_scan = await _site_with_scan(session, user)
    _, target_scan = await _site_with_scan(session, user, status=ScanStatus.RUNNING)

    finding = NormalizedFinding(
        source=FindingSource.ZAP,
        category=FindingCategory.SECURITY,
        rule_id="10020-1",
        title="Sin X-Frame-Options",
        severity=Severity.MEDIUM,
        confidence=Confidence.HIGH,
        description="Descripción",
    )
    session.add(
        Finding(
            scan_id=other_scan.id,
            source=finding.source,
            category=finding.category,
            rule_id=finding.rule_id,
            title=finding.title,
            severity=finding.severity,
            confidence=finding.confidence,
            description=finding.description,
            fingerprint=finding.fingerprint,
            status=FindingStatus.FALSE_POSITIVE,
        )
    )
    await session.commit()

    orchestrator = ScanOrchestrator(
        app.state.session_factory,  # type: ignore[attr-defined]
        app.state.redis,  # type: ignore[attr-defined]
        settings,  # type: ignore[arg-type]
    )
    await orchestrator._persist_findings(target_scan.id, [finding])

    status = await session.scalar(
        sa.select(Finding.status).where(Finding.scan_id == target_scan.id)
    )
    assert status is FindingStatus.OPEN
