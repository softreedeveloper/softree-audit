"""Validación de la configuración (`docs/spec/security.md` §10)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from softree_audit.core.config import (
    DEFAULT_SCORING_WEIGHTS,
    EXAMPLE_SECRET_KEY,
    Settings,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla la prueba del entorno.

    `_env_file=None` ignora el archivo .env, pero no las variables de entorno
    ya exportadas: sin esto, el resultado dependería de la configuración local
    de quien ejecuta las pruebas.
    """
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)


BASE: dict[str, object] = {
    "_env_file": None,
    "secret_key": "x" * 40,
    "database_url": "postgresql+asyncpg://user:pass@db:5432/softree",
    "redis_url": "redis://redis:6379/0",
}


def test_defaults_are_safe() -> None:
    settings = Settings(**BASE)  # type: ignore[arg-type]
    assert settings.app_url == "http://localhost:4321"
    assert settings.google_redirect_uri == (
        "http://localhost:8000/api/v1/integrations/google/callback"
    )
    assert settings.ssrf_allow_private_networks is False
    assert settings.ssrf_allowed_ports == [80, 443]
    assert settings.access_token_ttl_minutes == 15
    assert settings.refresh_token_ttl_days == 7
    assert settings.effective_scoring_weights == DEFAULT_SCORING_WEIGHTS


def test_production_rejects_example_secret_key() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(**{**BASE, "app_env": "production", "secret_key": EXAMPLE_SECRET_KEY})  # type: ignore[arg-type]
    assert "valor de ejemplo" in str(excinfo.value)


def test_production_rejects_short_secret_key() -> None:
    with pytest.raises(ValidationError):
        Settings(**{**BASE, "app_env": "production", "secret_key": "corta"})  # type: ignore[arg-type]


def test_production_rejects_private_network_access() -> None:
    """La bandera de desarrollo no debe poder quedar activa en producción."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(**{**BASE, "app_env": "production", "ssrf_allow_private_networks": True})  # type: ignore[arg-type]
    assert "SSRF_ALLOW_PRIVATE_NETWORKS" in str(excinfo.value)


def test_development_allows_example_secret_key() -> None:
    settings = Settings(**{**BASE, "app_env": "development", "secret_key": EXAMPLE_SECRET_KEY})  # type: ignore[arg-type]
    assert settings.app_env == "development"
    assert settings.cookie_secure is False


def test_cookie_is_secure_outside_development() -> None:
    assert Settings(**{**BASE, "app_env": "staging"}).cookie_secure is True  # type: ignore[arg-type]


def test_database_url_requires_async_driver() -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(**{**BASE, "database_url": "postgresql://user:pass@db:5432/softree"})  # type: ignore[arg-type]
    assert "asyncpg" in str(excinfo.value)


def test_cors_origins_accepts_comma_separated_list() -> None:
    settings = Settings(**{**BASE, "cors_origins": "https://a.test, https://b.test"})  # type: ignore[arg-type]
    assert settings.cors_origins == ["https://a.test", "https://b.test"]


def test_cors_origins_empty_string_means_same_origin() -> None:
    assert Settings(**{**BASE, "cors_origins": ""}).cors_origins == []  # type: ignore[arg-type]


def test_scoring_weights_from_json() -> None:
    settings = Settings(**{**BASE, "scoring_weights": '{"security":0.5,"seo":0.5}'})  # type: ignore[arg-type]
    assert settings.scoring_weights == {"security": 0.5, "seo": 0.5}
    # Las categorías no declaradas conservan su peso por defecto.
    assert settings.effective_scoring_weights["performance"] == 0.25


def test_scoring_weights_reject_unknown_category() -> None:
    with pytest.raises(ValidationError):
        Settings(**{**BASE, "scoring_weights": '{"desconocida":1.0}'})  # type: ignore[arg-type]


def test_scoring_weights_reject_negative_values() -> None:
    with pytest.raises(ValidationError):
        Settings(**{**BASE, "scoring_weights": '{"security":-0.1}'})  # type: ignore[arg-type]
