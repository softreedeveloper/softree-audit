"""Cliente del servicio de análisis con IA.

Habla con un endpoint compatible con la API de chat de Ollama: `POST /api/chat`
con `messages`, `stream: false` y `options`. La respuesta trae el texto en
`message.content` y contadores de tokens en `prompt_eval_count` y `eval_count`.

Es una integración externa más, con las reglas de RNF-02: timeout explícito,
reintentos acotados solo para errores transitorios, error normalizado y
degradación elegante. Si falla, el reporte se emite sin la sección de IA.
"""

from __future__ import annotations

import json
import re
import time
from types import TracebackType
from typing import Any

import httpx

from softree_audit.core.errors import AppError
from softree_audit.core.logging import get_logger
from softree_audit.services.ai.models import (
    PROMPT_VERSION,
    AiRecommendation,
    AiResult,
)
from softree_audit.services.common.retry import with_retry

logger = get_logger(__name__)

MAX_SUMMARY_CHARS = 1500
MAX_DETAIL_CHARS = 600
MAX_TITLE_CHARS = 160
MAX_RECOMMENDATIONS = 5
MAX_RISKS = 3

PRIORITIES = ("alta", "media", "baja")


class AiError(AppError):
    status_code = 502
    code = "ai_unavailable"
    message = "El servicio de análisis con IA no respondió."


class AiTransientError(AiError):
    """Fallo que puede desaparecer solo: corte de red, timeout o 5xx."""


class AiNotConfiguredError(AiError):
    code = "ai_not_configured"
    message = "El análisis con IA no está configurado: falta AI_API_URL o AI_API_KEY."


# Solo se reintenta lo transitorio. Una credencial rechazada o una respuesta
# ilegible dan el mismo resultado al segundo intento, así que no se repiten.
TRANSIENT_ERRORS = (AiTransientError,)


class AiClient:
    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 180.0,
        max_tokens: int = 900,
        temperature: float = 0.3,
    ) -> None:
        self._api_url = api_url
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        # `trust_env=False`: la configuración de proxy del entorno no debe
        # desviar una llamada que lleva una credencial.
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds), trust_env=False)

    async def __aenter__(self) -> AiClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def analyze(self, messages: list[dict[str, str]]) -> AiResult:
        started = time.perf_counter()
        payload = await with_retry(
            lambda: self._request(messages),
            retry_on=TRANSIENT_ERRORS,
            attempts=2,
            name="ai",
        )
        duration_ms = int((time.perf_counter() - started) * 1000)

        content = str((payload.get("message") or {}).get("content") or "").strip()
        if not content:
            raise AiError("El servicio de IA devolvió una respuesta vacía.")

        result = parse_response(content)
        result.model = str(payload.get("model") or self._model)
        result.prompt_version = PROMPT_VERSION
        result.duration_ms = duration_ms
        result.tokens_prompt = _as_int(payload.get("prompt_eval_count"))
        result.tokens_completion = _as_int(payload.get("eval_count"))

        logger.info(
            "ai.analysis_completed",
            model=result.model,
            duration_ms=duration_ms,
            recommendations=len(result.recommendations),
        )
        return result

    async def _request(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        try:
            response = await self._client.post(
                self._api_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_predict": self._max_tokens,
                        "temperature": self._temperature,
                    },
                },
            )
        except httpx.TimeoutException as exc:
            raise AiTransientError("El servicio de IA agotó el tiempo de espera.") from exc
        except httpx.TransportError as exc:
            raise AiTransientError("No fue posible contactar con el servicio de IA.") from exc

        if response.status_code in (401, 403):
            # No es transitorio: reintentar con la misma credencial no cambia nada.
            logger.warning("ai.unauthorized", status_code=response.status_code)
            raise AiNotConfiguredError("El servicio de IA rechazó la credencial.")
        if response.status_code >= 400:
            if response.status_code >= 500:
                raise AiTransientError(f"El servicio de IA respondió {response.status_code}.")
            raise AiError(f"El servicio de IA respondió {response.status_code}.")

        try:
            body = response.json()
        except ValueError as exc:
            raise AiError("El servicio de IA devolvió una respuesta ilegible.") from exc
        if not isinstance(body, dict):
            raise AiError("El servicio de IA devolvió una respuesta inesperada.")
        return body


def _as_int(value: object) -> int | None:
    return int(value) if isinstance(value, int) else None


def _clip(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def parse_response(content: str) -> AiResult:
    """Interpreta la respuesta del modelo.

    Se pide JSON, pero un modelo pequeño puede envolverlo en un bloque de
    código o añadir una frase. Si no hay JSON aprovechable, el texto se usa
    como resumen: es preferible entregar la redacción del modelo que descartar
    la llamada, y en ningún caso se inventa contenido.
    """
    data = _extract_json(content)
    if data is None:
        return AiResult(summary=_clip(content, MAX_SUMMARY_CHARS))

    recommendations: list[AiRecommendation] = []
    raw_recommendations = data.get("recommendations")
    if isinstance(raw_recommendations, list):
        for item in raw_recommendations[:MAX_RECOMMENDATIONS]:
            if not isinstance(item, dict):
                continue
            title = _clip(item.get("title"), MAX_TITLE_CHARS)
            if not title:
                continue
            priority = str(item.get("priority") or "").strip().lower()
            recommendations.append(
                AiRecommendation(
                    title=title,
                    detail=_clip(item.get("detail"), MAX_DETAIL_CHARS),
                    priority=priority if priority in PRIORITIES else "media",
                )
            )

    risks: list[str] = []
    raw_risks = data.get("risks")
    if isinstance(raw_risks, list):
        risks = [_clip(item, MAX_TITLE_CHARS) for item in raw_risks[:MAX_RISKS]]
        risks = [item for item in risks if item]

    summary = _clip(data.get("summary"), MAX_SUMMARY_CHARS)
    if not summary and not recommendations:
        # JSON válido pero sin nada útil: se conserva el texto original.
        return AiResult(summary=_clip(content, MAX_SUMMARY_CHARS))

    return AiResult(summary=summary, recommendations=recommendations, risks=risks)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(content: str) -> dict[str, Any] | None:
    candidates = [content]
    fenced = _FENCE.search(content)
    if fenced:
        candidates.insert(0, fenced.group(1))

    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end > start:
        candidates.append(content[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate.strip())
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
