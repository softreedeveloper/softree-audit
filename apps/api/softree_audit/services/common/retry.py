"""Reintentos acotados para integraciones externas.

`docs/spec/requirements.md` RNF-02: timeout, retry acotado, normalización de
error, logging y degradación elegante. Nunca reintentos infinitos.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

from softree_audit.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 0.5
DEFAULT_MAX_DELAY = 8.0


async def with_retry[T](
    operation: Callable[[], Awaitable[T]],
    *,
    retry_on: tuple[type[Exception], ...],
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    name: str = "operation",
) -> T:
    """Ejecuta `operation` reintentando solo los errores transitorios indicados.

    Espera exponencial con jitter, para no sincronizar reintentos entre tareas.
    """
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except retry_on as exc:
            last = exc
            if attempt == attempts:
                break
            delay = min(base_delay * 2 ** (attempt - 1), max_delay)
            delay += random.uniform(0, delay / 2)  # noqa: S311 - jitter, no criptográfico
            logger.info(
                "retry.scheduled",
                operation=name,
                attempt=attempt,
                attempts=attempts,
                delay_seconds=round(delay, 2),
                error=str(exc),
            )
            await asyncio.sleep(delay)

    assert last is not None
    logger.warning("retry.exhausted", operation=name, attempts=attempts, error=str(last))
    raise last
