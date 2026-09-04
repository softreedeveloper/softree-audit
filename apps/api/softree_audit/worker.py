"""Worker de arq: ejecuta el pipeline de scan fuera del proceso de la API.

Arranque:

    arq softree_audit.worker.WorkerSettings
"""

from __future__ import annotations

import uuid
from typing import Any

from softree_audit.core.config import get_settings
from softree_audit.core.logging import configure_logging, get_logger
from softree_audit.core.redis import RedisClient
from softree_audit.db.session import create_engine, create_session_factory
from softree_audit.scans.orchestrator import ScanOrchestrator
from softree_audit.scans.queue import QUEUE_NAME, redis_settings
from softree_audit.version import APP_VERSION, SCAN_ENGINE_VERSION

logger = get_logger(__name__)


async def run_scan(ctx: dict[str, Any], scan_id: str) -> str:
    orchestrator: ScanOrchestrator = ctx["orchestrator"]
    status = await orchestrator.run(uuid.UUID(scan_id))
    return status.value


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)

    engine = create_engine(settings)
    ctx["engine"] = engine
    ctx["redis_client"] = RedisClient.from_url(settings.redis_url, decode_responses=True)
    ctx["orchestrator"] = ScanOrchestrator(
        create_session_factory(engine), ctx["redis_client"], settings
    )
    logger.info(
        "worker.startup",
        app_version=APP_VERSION,
        engine_version=SCAN_ENGINE_VERSION,
        max_jobs=settings.worker_max_jobs,
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["redis_client"].aclose()
    await ctx["engine"].dispose()
    logger.info("worker.shutdown")


class WorkerSettings:
    """Configuración que arq lee por convención."""

    functions = [run_scan]  # noqa: RUF012 - contrato de arq
    on_startup = startup
    on_shutdown = shutdown
    queue_name = QUEUE_NAME
    max_jobs = get_settings().worker_max_jobs
    job_timeout = get_settings().scan_timeout_seconds
    # Un scan no debe reintentarse solo: repetiría tráfico contra el target.
    max_tries = 1
    keep_result = 3600
    redis_settings = redis_settings(get_settings())
