"""Contrato de los módulos del pipeline (`docs/spec/architecture.md` §3).

Un módulo recibe contexto, devuelve datos y no escribe en base de datos. El
orquestador es el único responsable de persistir, aplicar timeouts y capturar
excepciones, de modo que la falla de un módulo no cancele el scan completo.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from softree_audit.core.redis import RedisClient
from softree_audit.models.enums import ModuleName
from softree_audit.services.common.url_guard import ScopePolicy


@dataclass(slots=True)
class ScanContext:
    """Todo lo que un módulo necesita saber del scan en curso."""

    scan_id: uuid.UUID
    site_id: uuid.UUID
    base_url: str
    scope_snapshot: dict[str, Any]
    scope: ScopePolicy
    is_cancelled: Callable[[], Awaitable[bool]]
    # Compartido para cachés de integraciones externas (PageSpeed).
    redis: RedisClient | None = None
    # `(access_token, property_url)` de Search Console, ya resueltos por el
    # orquestador. `None` significa que el proyecto no tiene conexión.
    search_console: tuple[str, str | None] | None = None
    # Salidas de módulos anteriores, por nombre de módulo.
    artifacts: dict[str, Any] = field(default_factory=dict)

    def artifact(self, module: ModuleName) -> Any:
        return self.artifacts.get(module.value)


@dataclass(slots=True)
class ModuleResult:
    """Resultado de un módulo: datos a persistir y métricas de ejecución."""

    artifact: Any = None
    detail: dict[str, Any] = field(default_factory=dict)
    skipped: bool = False
    skip_reason: str | None = None


@runtime_checkable
class ScanModule(Protocol):
    """Interfaz común de todos los módulos del pipeline."""

    name: ModuleName

    async def run(self, context: ScanContext) -> ModuleResult: ...
