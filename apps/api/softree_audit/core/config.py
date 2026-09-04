"""Configuración de la aplicación.

Todo valor se lee de variables de entorno. No hay secretos con valor por
defecto: arrancar sin `SECRET_KEY` válida fuera de desarrollo es un error fatal.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "staging", "production"]

# Valor publicado en .env.example: existe para poder rechazarlo explícitamente.
EXAMPLE_SECRET_KEY = "CHANGE_ME_generate_a_real_random_value_of_at_least_32_chars"  # noqa: S105
MIN_SECRET_KEY_LENGTH = 32

DEFAULT_SCORING_WEIGHTS: dict[str, float] = {
    "security": 0.30,
    "performance": 0.25,
    "seo": 0.25,
    "accessibility": 0.10,
    "best_practices": 0.10,
}


class Settings(BaseSettings):
    """Configuración validada de la aplicación."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Entorno ────────────────────────────────────────────────────────────
    app_env: Environment = "development"
    app_url: str = "http://localhost:4321"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"
    api_prefix: str = "/api/v1"

    # ── Secretos ───────────────────────────────────────────────────────────
    secret_key: str = EXAMPLE_SECRET_KEY
    secret_key_previous: str | None = None

    # ── Persistencia ───────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://softree:softree@localhost:5432/softree_audit"
    test_database_url: str | None = None
    db_pool_size: Annotated[int, Field(ge=1, le=50)] = 5
    db_max_overflow: Annotated[int, Field(ge=0, le=50)] = 5
    db_echo: bool = False

    redis_url: str = "redis://localhost:6379/0"

    # ── Sesión ─────────────────────────────────────────────────────────────
    access_token_ttl_minutes: Annotated[int, Field(ge=1, le=1440)] = 15
    refresh_token_ttl_days: Annotated[int, Field(ge=1, le=90)] = 7
    refresh_cookie_name: str = "softree_refresh"

    # `NoDecode`: estos campos aceptan listas separadas por comas además de
    # JSON, así que el valor llega crudo al validador en lugar de pasar por el
    # decodificador JSON de pydantic-settings.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # ── Integraciones externas ─────────────────────────────────────────────
    zap_url: str | None = None
    zap_api_key: str | None = None
    zap_timeout_seconds: Annotated[int, Field(ge=30, le=7200)] = 900

    pagespeed_api_key: str | None = None
    pagespeed_cache_ttl_seconds: Annotated[int, Field(ge=0, le=86400)] = 21600

    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/api/v1/integrations/google/callback"

    # ── Scoring ────────────────────────────────────────────────────────────
    scoring_weights: Annotated[dict[str, float], NoDecode] = Field(
        default_factory=lambda: dict(DEFAULT_SCORING_WEIGHTS)
    )

    # ── Seguridad del scanner ──────────────────────────────────────────────
    ssrf_allow_private_networks: bool = False
    ssrf_allowed_ports: Annotated[list[int], NoDecode] = Field(default_factory=lambda: [80, 443])
    max_response_bytes: Annotated[int, Field(ge=1024, le=104_857_600)] = 5_242_880

    # ── Worker ─────────────────────────────────────────────────────────────
    worker_max_jobs: Annotated[int, Field(ge=1, le=16)] = 2
    scan_timeout_seconds: Annotated[int, Field(ge=60, le=86400)] = 3600

    # ── Reportes ───────────────────────────────────────────────────────────
    reports_dir: str = "/data/reports"

    # ── Validadores ────────────────────────────────────────────────────────

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Acepta una lista separada por comas o una lista JSON."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("ssrf_allowed_ports", mode="before")
    @classmethod
    def _split_ports(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return [80, 443]
            if stripped.startswith("["):
                return json.loads(stripped)
            return [int(item.strip()) for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("scoring_weights", mode="before")
    @classmethod
    def _parse_weights(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return dict(DEFAULT_SCORING_WEIGHTS)
            return json.loads(stripped)
        return value

    @field_validator("scoring_weights")
    @classmethod
    def _check_weights(cls, value: dict[str, float]) -> dict[str, float]:
        unknown = set(value) - set(DEFAULT_SCORING_WEIGHTS)
        if unknown:
            raise ValueError(f"Categorías de scoring desconocidas: {sorted(unknown)}")
        if any(weight < 0 for weight in value.values()):
            raise ValueError("Los pesos de scoring no pueden ser negativos")
        if sum(value.values()) <= 0:
            raise ValueError("La suma de los pesos de scoring debe ser mayor que cero")
        return value

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: str) -> str:
        # Validación de forma; el driver asíncrono es obligatorio para SQLAlchemy async.
        PostgresDsn(value.replace("+asyncpg", ""))
        if "+asyncpg" not in value:
            raise ValueError("DATABASE_URL debe usar el driver asíncrono postgresql+asyncpg")
        return value

    @field_validator("redis_url")
    @classmethod
    def _check_redis_url(cls, value: str) -> str:
        RedisDsn(value)
        return value

    @model_validator(mode="after")
    def _check_production_hardening(self) -> Settings:
        if self.app_env == "development":
            return self

        problems: list[str] = []
        if self.secret_key == EXAMPLE_SECRET_KEY:
            problems.append("SECRET_KEY conserva el valor de ejemplo")
        if len(self.secret_key) < MIN_SECRET_KEY_LENGTH:
            problems.append(f"SECRET_KEY debe tener al menos {MIN_SECRET_KEY_LENGTH} caracteres")
        if self.ssrf_allow_private_networks:
            problems.append("SSRF_ALLOW_PRIVATE_NETWORKS debe estar en false fuera de desarrollo")
        if problems:
            raise ValueError(
                f"Configuración inválida para APP_ENV={self.app_env}: " + "; ".join(problems)
            )
        return self

    # ── Derivados ──────────────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cookie_secure(self) -> bool:
        """La cookie de refresh solo viaja por HTTPS fuera de desarrollo."""
        return self.app_env != "development"

    @property
    def effective_scoring_weights(self) -> dict[str, float]:
        """Pesos completos: las categorías no declaradas toman su valor por defecto."""
        return {**DEFAULT_SCORING_WEIGHTS, **self.scoring_weights}


@lru_cache
def get_settings() -> Settings:
    """Configuración cacheada. Usar como dependencia de FastAPI."""
    return Settings()
