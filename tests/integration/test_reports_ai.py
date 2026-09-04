"""El reporte con análisis asistido por IA.

Lo que se verifica: que la sección aparece cuando el servicio responde, que no
aparece cuando no está configurado, que un fallo del servicio no impide entregar
el reporte, y que el texto no se reescribe en cada regeneración.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid

import httpx
import pytest
import respx
import sqlalchemy as sa
from httpx import AsyncClient
from softree_audit.core.config import Settings
from softree_audit.models import (
    AiAnalysis,
    ModuleName,
    ModuleStatus,
    Project,
    Scan,
    ScanModuleRun,
    ScanStatus,
    ScanType,
    Scope,
    Site,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

REPORTS = "/api/v1/reports"
AI_ENDPOINT = "https://agente-ia.example.test/api/chat"

ANSWER = {
    "summary": "El sitio está razonablemente cuidado, con cabeceras de seguridad pendientes.",
    "risks": ["Ausencia de Content Security Policy"],
    "recommendations": [
        {
            "title": "Definir una Content Security Policy",
            "detail": "Reduce el impacto de un XSS. Empezar en modo report-only.",
            "priority": "alta",
        }
    ],
}


def _ai_response(content: str | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "qwen2.5:7b",
            "message": {
                "role": "assistant",
                "content": content if content is not None else json.dumps(ANSWER),
            },
            "done": True,
            "prompt_eval_count": 700,
            "eval_count": 120,
        },
    )


def _with_ai(app: object, settings: Settings) -> Settings:
    """Configura el servicio de IA solo para la prueba en curso."""
    original: Settings = app.state.settings  # type: ignore[attr-defined]
    app.state.settings = Settings(  # type: ignore[attr-defined]
        _env_file=None,
        app_env="development",
        secret_key=settings.secret_key,
        database_url=settings.database_url,
        redis_url=settings.redis_url,
        reports_dir=settings.reports_dir,
        ssrf_allow_private_networks=False,
        ai_api_url=AI_ENDPOINT,
        ai_api_key="clave-de-prueba",
        ai_model="qwen2.5:7b",
    )
    return original


async def _scan(session: AsyncSession, owner: User) -> Scan:
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
        status=ScanStatus.COMPLETED,
        progress=100,
        started_at=dt.datetime(2026, 9, 4, 10, 0, tzinfo=dt.UTC),
        finished_at=dt.datetime(2026, 9, 4, 10, 5, tzinfo=dt.UTC),
        duration_ms=300_000,
        scope_snapshot={"base_url": site.base_url},
        engine_version="0.1.0",
        app_version="0.1.0",
    )
    session.add(scan)
    await session.flush()

    session.add(
        ScanModuleRun(
            scan_id=scan.id,
            module=ModuleName.CRAWLER,
            status=ModuleStatus.COMPLETED,
            duration_ms=1200,
        )
    )
    await session.commit()
    return scan


@respx.mock
async def test_the_report_includes_the_ai_section(
    auth_client: AsyncClient,
    user: User,
    app_context: tuple[object, AsyncSession],
    settings: Settings,
) -> None:
    app, session = app_context
    scan = await _scan(session, user)
    original = _with_ai(app, settings)
    respx.post(AI_ENDPOINT).mock(return_value=_ai_response())

    try:
        response = await auth_client.post(
            f"{REPORTS}/{scan.id}/generate", json={"formats": ["html", "json"]}
        )
        assert response.status_code == 201

        html = (await auth_client.get(f"{REPORTS}/{scan.id}/download?format=html")).text
        payload = json.loads(
            (await auth_client.get(f"{REPORTS}/{scan.id}/download?format=json")).content
        )
    finally:
        app.state.settings = original  # type: ignore[attr-defined]

    assert "Análisis asistido por IA" in html
    assert "Definir una Content Security Policy" in html
    assert "Ausencia de Content Security Policy" in html
    # El origen del texto se declara siempre.
    assert "lo redactó un modelo de lenguaje" in html
    assert "qwen2.5:7b" in html

    assert payload["ai_analysis"]["summary"].startswith("El sitio está razonablemente")
    assert payload["ai_analysis"]["recommendations"][0]["priority"] == "alta"


@respx.mock
async def test_the_analysis_is_stored_with_its_traceability(
    auth_client: AsyncClient,
    user: User,
    app_context: tuple[object, AsyncSession],
    settings: Settings,
) -> None:
    app, session = app_context
    scan = await _scan(session, user)
    original = _with_ai(app, settings)
    respx.post(AI_ENDPOINT).mock(return_value=_ai_response())

    try:
        await auth_client.post(f"{REPORTS}/{scan.id}/generate", json={"formats": ["json"]})
    finally:
        app.state.settings = original  # type: ignore[attr-defined]

    analysis = await session.scalar(sa.select(AiAnalysis).where(AiAnalysis.scan_id == scan.id))
    assert analysis is not None
    assert analysis.model == "qwen2.5:7b"
    assert analysis.prompt_version == "v1"
    assert analysis.tokens_prompt == 700
    assert analysis.tokens_completion == 120
    assert analysis.duration_ms is not None


@respx.mock
async def test_regenerating_does_not_call_the_model_again(
    auth_client: AsyncClient,
    user: User,
    app_context: tuple[object, AsyncSession],
    settings: Settings,
) -> None:
    """Un reporte ya entregado no debe cambiar de redacción al regenerarlo."""
    app, session = app_context
    scan = await _scan(session, user)
    original = _with_ai(app, settings)
    route = respx.post(AI_ENDPOINT).mock(return_value=_ai_response())

    try:
        await auth_client.post(f"{REPORTS}/{scan.id}/generate", json={"formats": ["json"]})
        await auth_client.post(f"{REPORTS}/{scan.id}/generate", json={"formats": ["html"]})
        await auth_client.post(
            f"{REPORTS}/{scan.id}/generate",
            json={"formats": ["json"], "audience": "executive"},
        )
    finally:
        app.state.settings = original  # type: ignore[attr-defined]

    assert route.call_count == 1


@respx.mock
async def test_a_failing_ai_service_does_not_block_the_report(
    auth_client: AsyncClient,
    user: User,
    app_context: tuple[object, AsyncSession],
    settings: Settings,
) -> None:
    """Degradación elegante: mejor un reporte sin la sección que ningún reporte."""
    app, session = app_context
    scan = await _scan(session, user)
    original = _with_ai(app, settings)
    respx.post(AI_ENDPOINT).mock(return_value=httpx.Response(503))

    try:
        response = await auth_client.post(
            f"{REPORTS}/{scan.id}/generate", json={"formats": ["json"]}
        )
    finally:
        app.state.settings = original  # type: ignore[attr-defined]

    assert response.status_code == 201
    payload = json.loads(
        (await auth_client.get(f"{REPORTS}/{scan.id}/download?format=json")).content
    )
    assert payload["ai_analysis"] is None
    assert await session.scalar(sa.select(AiAnalysis).where(AiAnalysis.scan_id == scan.id)) is None


async def test_without_configuration_there_is_no_section_and_no_call(
    auth_client: AsyncClient, user: User, app_context: tuple[object, AsyncSession]
) -> None:
    """Sin credenciales no se llama a nada ni se inventa el análisis."""
    _, session = app_context
    scan = await _scan(session, user)

    with respx.mock:
        route = respx.post(AI_ENDPOINT).mock(return_value=_ai_response())
        response = await auth_client.post(
            f"{REPORTS}/{scan.id}/generate", json={"formats": ["html"]}
        )
        assert route.call_count == 0

    assert response.status_code == 201
    html = (await auth_client.get(f"{REPORTS}/{scan.id}/download?format=html")).text
    assert "Análisis asistido por IA" not in html


@respx.mock
@pytest.mark.security
async def test_the_evidence_of_the_audited_site_is_not_sent(
    auth_client: AsyncClient,
    user: User,
    app_context: tuple[object, AsyncSession],
    settings: Settings,
) -> None:
    """El contenido del sitio auditado se asume hostil: viaja lo mínimo."""
    app, session = app_context
    scan = await _scan(session, user)
    original = _with_ai(app, settings)
    route = respx.post(AI_ENDPOINT).mock(return_value=_ai_response())

    try:
        await auth_client.post(f"{REPORTS}/{scan.id}/generate", json={"formats": ["json"]})
    finally:
        app.state.settings = original  # type: ignore[attr-defined]

    sent = json.loads(route.calls[0].request.content)
    system = sent["messages"][0]["content"]
    user_message = sent["messages"][1]["content"]

    assert "no es de confianza" in system
    assert "<datos_auditoria>" in user_message
    assert sent["stream"] is False


@respx.mock
@pytest.mark.security
async def test_the_model_cannot_dictate_how_much_it_occupies(
    auth_client: AsyncClient,
    user: User,
    app_context: tuple[object, AsyncSession],
    settings: Settings,
) -> None:
    """Una respuesta desmedida se recorta antes de llegar al documento."""
    app, session = app_context
    scan = await _scan(session, user)
    original = _with_ai(app, settings)
    respx.post(AI_ENDPOINT).mock(return_value=_ai_response("R" * 20000))

    try:
        await auth_client.post(f"{REPORTS}/{scan.id}/generate", json={"formats": ["json"]})
    finally:
        app.state.settings = original  # type: ignore[attr-defined]

    analysis = await session.scalar(sa.select(AiAnalysis).where(AiAnalysis.scan_id == scan.id))
    assert analysis is not None
    assert len(analysis.summary) <= 1500
