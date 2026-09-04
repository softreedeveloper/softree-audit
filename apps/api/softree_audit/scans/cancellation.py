"""Señal de cancelación de un scan.

Bandera en Redis: la API la marca y el worker la consulta entre etapas y dentro
del bucle del crawler (`docs/spec/architecture.md` §4).
"""

from __future__ import annotations

import uuid

from redis.exceptions import RedisError

from softree_audit.core.logging import get_logger
from softree_audit.core.redis import RedisClient

logger = get_logger(__name__)

# La bandera solo tiene sentido mientras el scan pueda estar en marcha.
TTL_SECONDS = 24 * 3600


def _key(scan_id: uuid.UUID) -> str:
    return f"scan:cancel:{scan_id}"


async def request_cancel(redis: RedisClient, scan_id: uuid.UUID) -> None:
    await redis.set(_key(scan_id), "1", ex=TTL_SECONDS)


async def is_cancelled(redis: RedisClient, scan_id: uuid.UUID) -> bool:
    try:
        return bool(await redis.exists(_key(scan_id)))
    except RedisError as exc:
        # Si Redis no responde, el scan continúa: interrumpirlo por una falla de
        # infraestructura perdería el trabajo ya hecho.
        logger.warning("scan.cancel_check_failed", scan_id=str(scan_id), error=str(exc))
        return False


async def clear_cancel(redis: RedisClient, scan_id: uuid.UUID) -> None:
    try:
        await redis.delete(_key(scan_id))
    except RedisError:
        logger.info("scan.cancel_clear_failed", scan_id=str(scan_id))
