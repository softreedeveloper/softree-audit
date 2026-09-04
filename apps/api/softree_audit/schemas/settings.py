"""Esquemas de la configuración de la instancia."""

from __future__ import annotations

from pydantic import Field

from softree_audit.schemas.common import ApiModel


class ScoringWeights(ApiModel):
    """Pesos del Softree Score, tal como están configurados (§26)."""

    security: float
    performance: float
    seo: float
    accessibility: float
    best_practices: float


class IntegrationStatus(ApiModel):
    key: str
    name: str
    configured: bool = Field(description="Si hay credenciales. Nunca se devuelve su valor.")
    detail: str
    variables: list[str]


class ScopeDefaults(ApiModel):
    """Máximos que ningún scope puede superar."""

    max_pages: int
    max_depth: int
    timeout_seconds: int
    request_delay_ms: int
    concurrency: int


class InstanceSettings(ApiModel):
    environment: str
    app_version: str
    scan_engine_version: str
    report_version: str

    user_email: str
    user_full_name: str

    scoring: ScoringWeights
    integrations: list[IntegrationStatus]
    scope_defaults: ScopeDefaults

    ssrf_allow_private_networks: bool
    allowed_ports: list[int]
    access_token_ttl_minutes: int
    refresh_token_ttl_days: int
