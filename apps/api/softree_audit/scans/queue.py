"""Encolado de scans con arq (ADR-003)."""

from __future__ import annotations

import uuid

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from softree_audit.core.config import Settings
from softree_audit.core.logging import get_logger

logger = get_logger(__name__)

RUN_SCAN_TASK = "run_scan"
QUEUE_NAME = "softree:scans"


def redis_settings(settings: Settings) -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def create_queue(settings: Settings) -> ArqRedis:
    return await create_pool(redis_settings(settings), default_queue_name=QUEUE_NAME)


async def enqueue_scan(queue: ArqRedis, scan_id: uuid.UUID) -> None:
    """Encola el scan. El payload es mínimo: el worker relee el estado de la base."""
    await queue.enqueue_job(RUN_SCAN_TASK, str(scan_id), _job_id=f"scan:{scan_id}")
    logger.info("scan.enqueued", scan_id=str(scan_id))
