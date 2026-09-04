"""Esquemas del scope de crawling.

Los máximos coinciden con los `CHECK` de la base de datos: el usuario puede
bajarlos, nunca superarlos (`docs/spec/database.md` §scopes).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from pydantic import Field, field_validator

from softree_audit.models.site import (
    MAX_CONCURRENCY,
    MAX_DEPTH_LIMIT,
    MAX_PAGES_LIMIT,
    MAX_REQUEST_DELAY_MS,
    MAX_TIMEOUT_SECONDS,
)
from softree_audit.schemas.common import ApiModel
from softree_audit.services.common.urls import (
    InvalidHostnameError,
    InvalidPathError,
    normalize_hostname,
    normalize_path,
)

MAX_DOMAINS = 20
MAX_PATHS = 50


def _normalize_domains(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        try:
            host = normalize_hostname(value)
        except InvalidHostnameError as exc:
            raise ValueError(f"Dominio inválido «{value}»: {exc}") from exc
        if host not in normalized:
            normalized.append(host)
    return normalized


def _normalize_paths(values: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        try:
            path = normalize_path(value)
        except InvalidPathError as exc:
            raise ValueError(f"Ruta inválida «{value}»: {exc}") from exc
        if path not in normalized:
            normalized.append(path)
    return normalized


class ScopeUpdate(ApiModel):
    """Configuración de alcance del crawling."""

    allowed_domains: Annotated[list[str], Field(min_length=1, max_length=MAX_DOMAINS)]
    allowed_paths: Annotated[list[str], Field(default_factory=list, max_length=MAX_PATHS)]
    excluded_paths: Annotated[list[str], Field(default_factory=list, max_length=MAX_PATHS)]

    max_pages: Annotated[int, Field(ge=1, le=MAX_PAGES_LIMIT)] = 200
    max_depth: Annotated[int, Field(ge=1, le=MAX_DEPTH_LIMIT)] = 3
    timeout_seconds: Annotated[int, Field(ge=1, le=MAX_TIMEOUT_SECONDS)] = 20
    request_delay_ms: Annotated[int, Field(ge=0, le=MAX_REQUEST_DELAY_MS)] = 200
    concurrency: Annotated[int, Field(ge=1, le=MAX_CONCURRENCY)] = 4

    respect_robots: bool = True
    zap_spider_enabled: bool = True
    check_external_links: bool = False

    @field_validator("allowed_domains")
    @classmethod
    def _check_domains(cls, value: list[str]) -> list[str]:
        return _normalize_domains(value)

    @field_validator("allowed_paths", "excluded_paths")
    @classmethod
    def _check_paths(cls, value: list[str]) -> list[str]:
        return _normalize_paths(value)


class ScopeRead(ApiModel):
    id: uuid.UUID
    site_id: uuid.UUID
    allowed_domains: list[str]
    allowed_paths: list[str]
    excluded_paths: list[str]
    max_pages: int
    max_depth: int
    timeout_seconds: int
    request_delay_ms: int
    concurrency: int
    respect_robots: bool
    zap_spider_enabled: bool
    check_external_links: bool
    created_at: dt.datetime
    updated_at: dt.datetime


class ScopeLimits(ApiModel):
    """Máximos que la interfaz debe respetar, servidos por la propia API."""

    max_pages: int = MAX_PAGES_LIMIT
    max_depth: int = MAX_DEPTH_LIMIT
    timeout_seconds: int = MAX_TIMEOUT_SECONDS
    request_delay_ms: int = MAX_REQUEST_DELAY_MS
    concurrency: int = MAX_CONCURRENCY
    domains: int = MAX_DOMAINS
    paths: int = MAX_PATHS
