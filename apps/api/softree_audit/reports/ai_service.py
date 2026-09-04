"""Generación y almacenamiento del análisis con IA de una auditoría.

Se ejecuta al generar el reporte, no durante el scan: necesita los hallazgos ya
deduplicados y las puntuaciones ya calculadas, que es justo lo que contiene el
`ReportModel`.

El análisis se guarda una vez por auditoría. Regenerar un formato distinto, o
volver a descargar el PDF, reutiliza el texto almacenado: un reporte entregado
no debe cambiar de redacción a espaldas de quien lo entregó.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import asdict

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from softree_audit.core.config import Settings
from softree_audit.core.logging import get_logger
from softree_audit.models import AiAnalysis
from softree_audit.services.ai.client import AiClient, AiError
from softree_audit.services.ai.models import AiResult
from softree_audit.services.ai.prompt import build_messages
from softree_audit.services.reports.model import (
    AiRecommendationBlock,
    ReportAnalysis,
    ReportModel,
)

logger = get_logger(__name__)


class AiAnalysisService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    @property
    def configured(self) -> bool:
        return bool(self._settings.ai_api_url and self._settings.ai_api_key)

    async def ensure(self, scan_id: uuid.UUID, model: ReportModel) -> ReportAnalysis | None:
        """Devuelve el análisis de la auditoría, generándolo si hace falta.

        Nunca propaga un fallo: si el servicio de IA no responde, el reporte se
        emite sin la sección. Es preferible a bloquear la entrega o, peor, a
        rellenarla con texto inventado.
        """
        if model.ai_analysis is not None:
            return model.ai_analysis
        if not self.configured:
            return None

        try:
            result = await self._generate(model)
        except AiError as exc:
            logger.warning("ai.analysis_failed", scan_id=str(scan_id), reason=exc.code)
            return None

        stored = await self._store(scan_id, result)
        analysis = ReportAnalysis(
            summary=stored.summary,
            recommendations=[
                AiRecommendationBlock(
                    title=str(item.get("title", "")),
                    detail=str(item.get("detail", "")),
                    priority=str(item.get("priority", "media")),
                )
                for item in stored.recommendations
            ],
            risks=[str(item) for item in stored.risks],
            model=stored.model,
            generated_at=stored.generated_at,
        )
        model.ai_analysis = analysis
        return analysis

    async def _generate(self, model: ReportModel) -> AiResult:
        assert self._settings.ai_api_url and self._settings.ai_api_key
        async with AiClient(
            api_url=self._settings.ai_api_url,
            api_key=self._settings.ai_api_key,
            model=self._settings.ai_model,
            timeout_seconds=float(self._settings.ai_timeout_seconds),
            max_tokens=self._settings.ai_max_tokens,
            temperature=self._settings.ai_temperature,
        ) as client:
            return await client.analyze(build_messages(model))

    async def _store(self, scan_id: uuid.UUID, result: AiResult) -> AiAnalysis:
        recommendations = [asdict(item) for item in result.recommendations]
        existing = await self._session.scalar(
            sa.select(AiAnalysis).where(AiAnalysis.scan_id == scan_id)
        )

        if existing is not None:
            existing.model = result.model
            existing.prompt_version = result.prompt_version
            existing.summary = result.summary
            existing.recommendations = recommendations
            existing.risks = list(result.risks)
            existing.duration_ms = result.duration_ms
            existing.tokens_prompt = result.tokens_prompt
            existing.tokens_completion = result.tokens_completion
            existing.generated_at = dt.datetime.now(dt.UTC)
            await self._session.flush()
            return existing

        analysis = AiAnalysis(
            scan_id=scan_id,
            model=result.model,
            prompt_version=result.prompt_version,
            summary=result.summary,
            recommendations=recommendations,
            risks=list(result.risks),
            duration_ms=result.duration_ms,
            tokens_prompt=result.tokens_prompt,
            tokens_completion=result.tokens_completion,
            generated_at=dt.datetime.now(dt.UTC),
        )
        self._session.add(analysis)
        await self._session.flush()
        logger.info("ai.analysis_stored", scan_id=str(scan_id), model=analysis.model)
        return analysis
