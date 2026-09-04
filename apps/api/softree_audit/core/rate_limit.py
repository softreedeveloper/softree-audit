"""Límites de tasa con ventana deslizante sobre Redis.

Política y valores en `docs/spec/security.md` §5. Ante una falla de Redis:
fail closed en autenticación, fail open en el resto.
"""

from __future__ import annotations

import contextlib
import time
import uuid
from dataclasses import dataclass

from redis.exceptions import RedisError

from softree_audit.core.errors import RateLimitedError, ServiceUnavailableError
from softree_audit.core.logging import get_logger
from softree_audit.core.redis import RedisClient

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """Límite de `max_requests` peticiones por `window_seconds`."""

    name: str
    max_requests: int
    window_seconds: int
    fail_closed: bool = False


# Políticas declaradas en security.md §5.
LOGIN = RateLimitPolicy("login", max_requests=5, window_seconds=900, fail_closed=True)
REFRESH = RateLimitPolicy("refresh", max_requests=30, window_seconds=3600, fail_closed=True)
SCAN_CREATE = RateLimitPolicy("scan_create", max_requests=10, window_seconds=3600)
REPORT_GENERATE = RateLimitPolicy("report_generate", max_requests=20, window_seconds=3600)
DEFAULT = RateLimitPolicy("default", max_requests=300, window_seconds=60)


class RateLimiter:
    """Ventana deslizante implementada con un sorted set por clave."""

    def __init__(self, redis: RedisClient) -> None:
        self._redis = redis

    async def check(self, policy: RateLimitPolicy, identifier: str) -> None:
        """Registra un intento y lanza `RateLimitedError` si excede la política."""
        key = f"ratelimit:{policy.name}:{identifier}"
        now_ms = int(time.time() * 1000)
        window_ms = policy.window_seconds * 1000
        cutoff = now_ms - window_ms

        try:
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)
            # Miembro único: cada intento debe contar por separado dentro de la ventana.
            pipe.zadd(key, {f"{now_ms}:{uuid.uuid4().hex}": now_ms})
            pipe.zcard(key)
            pipe.pexpire(key, window_ms)
            results = await pipe.execute()
            count = int(results[2])
        except RedisError as exc:
            logger.error(
                "rate_limit.backend_unavailable",
                policy=policy.name,
                fail_closed=policy.fail_closed,
                error=str(exc),
            )
            if policy.fail_closed:
                raise ServiceUnavailableError(
                    "El control de acceso no está disponible en este momento."
                ) from exc
            return

        if count > policy.max_requests:
            oldest = await self._oldest_timestamp(key)
            retry_after = policy.window_seconds
            if oldest is not None:
                retry_after = max(1, int((oldest + window_ms - now_ms) / 1000) + 1)
            logger.warning(
                "rate_limit.exceeded",
                policy=policy.name,
                identifier=identifier,
                count=count,
                limit=policy.max_requests,
            )
            raise RateLimitedError(retry_after)

    async def reset(self, policy: RateLimitPolicy, identifier: str) -> None:
        """Limpia el contador. Se usa tras un login exitoso.

        Es best effort: si Redis falla, el límite sigue vigente hasta que
        expire la ventana.
        """
        with contextlib.suppress(RedisError):
            await self._redis.delete(f"ratelimit:{policy.name}:{identifier}")

    async def _oldest_timestamp(self, key: str) -> int | None:
        try:
            entries = await self._redis.zrange(key, 0, 0, withscores=True)
        except RedisError:
            return None
        if not entries:
            return None
        return int(entries[0][1])
