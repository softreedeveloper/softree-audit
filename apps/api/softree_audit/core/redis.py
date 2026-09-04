"""Alias del cliente de Redis.

`redis.asyncio.Redis` es genérico solo en los stubs de tipos: en tiempo de
ejecución no acepta parámetros. FastAPI evalúa las anotaciones de las
dependencias en tiempo de ejecución, así que `Redis[str]` rompería la
construcción de las rutas. Este alias satisface a mypy y al intérprete.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from redis.asyncio import Redis

if TYPE_CHECKING:
    RedisClient = Redis[str]
else:
    RedisClient = Redis

__all__ = ["RedisClient"]
