"""Esquemas compartidos."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    """Base de todos los esquemas expuestos por la API."""

    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True)


class ErrorDetail(ApiModel):
    code: str = Field(description="Código estable de error, apto para lógica de cliente.")
    message: str = Field(description="Mensaje presentable al usuario.")
    details: Any = Field(default=None, description="Información adicional, opcional.")


class ErrorResponse(ApiModel):
    error: ErrorDetail


class Page[ItemT](ApiModel):
    """Página de resultados con cursor opaco."""

    items: list[ItemT]
    next_cursor: str | None = None
    total: int | None = None


class HealthResponse(ApiModel):
    status: str
    environment: str
    app_version: str
    scan_engine_version: str
    report_version: str
    database: str
    redis: str
    ssrf_allow_private_networks: bool
