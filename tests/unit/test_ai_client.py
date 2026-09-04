"""Cliente del servicio de IA: contrato real, degradación y saneado de salida."""

from __future__ import annotations

import httpx
import pytest
import respx
from softree_audit.services.ai.client import (
    MAX_RECOMMENDATIONS,
    MAX_SUMMARY_CHARS,
    AiClient,
    AiError,
    AiNotConfiguredError,
    parse_response,
)

pytestmark = pytest.mark.unit

ENDPOINT = "https://agente-ia.example.test/api/chat"

VALID_CONTENT = (
    '{"summary": "El sitio está en buen estado general.", '
    '"risks": ["Cabeceras de seguridad ausentes"], '
    '"recommendations": [{"title": "Definir CSP", "detail": "Reduce el impacto de un XSS.", '
    '"priority": "alta"}]}'
)


def _ollama_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "qwen2.5:7b",
            "message": {"role": "assistant", "content": content},
            "done": True,
            "prompt_eval_count": 812,
            "eval_count": 140,
        },
    )


def _client(**overrides: object) -> AiClient:
    defaults: dict[str, object] = {
        "api_url": ENDPOINT,
        "api_key": "clave-de-prueba",
        "model": "qwen2.5:7b",
        "timeout_seconds": 5.0,
    }
    return AiClient(**{**defaults, **overrides})  # type: ignore[arg-type]


# ── Contrato con el servicio ───────────────────────────────────────────────


@respx.mock
async def test_sends_the_documented_request() -> None:
    route = respx.post(ENDPOINT).mock(return_value=_ollama_response(VALID_CONTENT))

    async with _client() as client:
        await client.analyze([{"role": "user", "content": "hola"}])

    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer clave-de-prueba"
    assert request.headers["content-type"] == "application/json"

    import json

    body = json.loads(request.content)
    assert body["model"] == "qwen2.5:7b"
    assert body["stream"] is False
    assert body["options"]["num_predict"] > 0
    assert 0.0 <= body["options"]["temperature"] <= 1.0


@respx.mock
async def test_reads_the_answer_and_its_traceability() -> None:
    respx.post(ENDPOINT).mock(return_value=_ollama_response(VALID_CONTENT))

    async with _client() as client:
        result = await client.analyze([{"role": "user", "content": "hola"}])

    assert result.summary == "El sitio está en buen estado general."
    assert result.risks == ["Cabeceras de seguridad ausentes"]
    assert result.recommendations[0].title == "Definir CSP"
    assert result.recommendations[0].priority == "alta"
    assert result.model == "qwen2.5:7b"
    assert result.tokens_prompt == 812
    assert result.tokens_completion == 140
    assert result.duration_ms is not None


# ── Degradación ────────────────────────────────────────────────────────────


@respx.mock
async def test_a_rejected_credential_is_not_retried() -> None:
    """Reintentar con la misma clave no cambiaría nada."""
    route = respx.post(ENDPOINT).mock(return_value=httpx.Response(401, json={"error": "no"}))

    async with _client() as client:
        with pytest.raises(AiNotConfiguredError):
            await client.analyze([{"role": "user", "content": "hola"}])

    assert route.call_count == 1


@respx.mock
async def test_a_server_error_is_retried_and_then_reported() -> None:
    route = respx.post(ENDPOINT).mock(return_value=httpx.Response(503))

    async with _client() as client:
        with pytest.raises(AiError):
            await client.analyze([{"role": "user", "content": "hola"}])

    assert route.call_count == 2


@respx.mock
async def test_a_timeout_becomes_a_normalised_error() -> None:
    respx.post(ENDPOINT).mock(side_effect=httpx.ReadTimeout("timeout"))

    async with _client() as client:
        with pytest.raises(AiError) as excinfo:
            await client.analyze([{"role": "user", "content": "hola"}])

    assert excinfo.value.code == "ai_unavailable"


@respx.mock
async def test_an_empty_answer_is_an_error_not_an_empty_section() -> None:
    respx.post(ENDPOINT).mock(return_value=_ollama_response("   "))

    async with _client() as client:
        with pytest.raises(AiError):
            await client.analyze([{"role": "user", "content": "hola"}])


@respx.mock
async def test_an_unreadable_body_is_an_error() -> None:
    respx.post(ENDPOINT).mock(return_value=httpx.Response(200, text="no soy json"))

    async with _client() as client:
        with pytest.raises(AiError):
            await client.analyze([{"role": "user", "content": "hola"}])


# ── Saneado de la salida del modelo ────────────────────────────────────────


def test_json_inside_a_code_fence_is_understood() -> None:
    result = parse_response(f"```json\n{VALID_CONTENT}\n```")

    assert result.summary == "El sitio está en buen estado general."
    assert len(result.recommendations) == 1


def test_json_with_a_preamble_is_understood() -> None:
    result = parse_response(f"Claro, aquí tienes el análisis:\n{VALID_CONTENT}")

    assert result.recommendations[0].title == "Definir CSP"


def test_plain_prose_becomes_the_summary() -> None:
    """Antes que descartar la llamada, se entrega lo que el modelo escribió."""
    result = parse_response("El sitio tiene tres problemas de seguridad relevantes.")

    assert result.summary == "El sitio tiene tres problemas de seguridad relevantes."
    assert result.recommendations == []


def test_an_unknown_priority_falls_back_to_media() -> None:
    result = parse_response(
        '{"summary": "x", "recommendations": [{"title": "T", "detail": "D", '
        '"priority": "URGENTÍSIMA"}]}'
    )

    assert result.recommendations[0].priority == "media"


def test_the_output_of_the_model_is_bounded() -> None:
    """El modelo no decide cuánto ocupa en el reporte."""
    result = parse_response(
        '{"summary": "'
        + "x" * 9000
        + '", "recommendations": '
        + str([{"title": f"T{i}", "detail": "d", "priority": "alta"} for i in range(40)]).replace(
            "'", '"'
        )
        + "}"
    )

    assert len(result.summary) == MAX_SUMMARY_CHARS
    assert len(result.recommendations) == MAX_RECOMMENDATIONS


def test_a_malformed_recommendation_is_discarded_not_guessed() -> None:
    result = parse_response(
        '{"summary": "x", "recommendations": ["texto suelto", {"detail": "sin titulo"}, '
        '{"title": "Válida", "detail": "ok", "priority": "baja"}]}'
    )

    assert [item.title for item in result.recommendations] == ["Válida"]
