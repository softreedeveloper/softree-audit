"""Configuración efectiva de la instancia.

Permite ver desde la interfaz cómo está configurada la plataforma sin exponer
ningún secreto: solo si cada integración tiene credenciales, nunca su valor.
"""

from __future__ import annotations

from fastapi import APIRouter

from softree_audit.api.deps import AppSettings, CurrentUser
from softree_audit.models.site import (
    MAX_CONCURRENCY,
    MAX_DEPTH_LIMIT,
    MAX_PAGES_LIMIT,
    MAX_REQUEST_DELAY_MS,
    MAX_TIMEOUT_SECONDS,
)
from softree_audit.schemas.settings import (
    InstanceSettings,
    IntegrationStatus,
    ScopeDefaults,
    ScoringWeights,
)
from softree_audit.version import APP_VERSION, REPORT_VERSION, SCAN_ENGINE_VERSION

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=InstanceSettings, summary="Configuración de la instancia")
async def instance_settings(user: CurrentUser, settings: AppSettings) -> InstanceSettings:
    """Configuración efectiva. Nunca devuelve secretos, solo si están presentes."""
    weights = settings.effective_scoring_weights

    return InstanceSettings(
        environment=settings.app_env,
        app_version=APP_VERSION,
        scan_engine_version=SCAN_ENGINE_VERSION,
        report_version=REPORT_VERSION,
        user_email=user.email,
        user_full_name=user.full_name,
        scoring=ScoringWeights(
            security=weights["security"],
            performance=weights["performance"],
            seo=weights["seo"],
            accessibility=weights["accessibility"],
            best_practices=weights["best_practices"],
        ),
        integrations=[
            IntegrationStatus(
                key="zap",
                name="OWASP ZAP",
                configured=bool(settings.zap_url),
                detail=(
                    "Análisis pasivo de seguridad."
                    if settings.zap_url
                    else "Defina ZAP_URL y ZAP_API_KEY para habilitar el módulo de seguridad."
                ),
                variables=["ZAP_URL", "ZAP_API_KEY"],
            ),
            IntegrationStatus(
                key="pagespeed",
                name="Google PageSpeed Insights",
                configured=bool(settings.pagespeed_api_key),
                detail=(
                    "Clave configurada."
                    if settings.pagespeed_api_key
                    else (
                        "Sin PAGESPEED_API_KEY se usa la cuota anónima compartida de Google, "
                        "que suele estar agotada."
                    )
                ),
                variables=["PAGESPEED_API_KEY"],
            ),
            IntegrationStatus(
                key="search_console",
                name="Google Search Console",
                configured=bool(settings.google_client_id and settings.google_client_secret),
                detail=(
                    "Credenciales OAuth configuradas. La conexión se hace por proyecto."
                    if settings.google_client_id and settings.google_client_secret
                    else "Defina GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET para poder conectar."
                ),
                variables=["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"],
            ),
        ],
        scope_defaults=ScopeDefaults(
            max_pages=MAX_PAGES_LIMIT,
            max_depth=MAX_DEPTH_LIMIT,
            timeout_seconds=MAX_TIMEOUT_SECONDS,
            request_delay_ms=MAX_REQUEST_DELAY_MS,
            concurrency=MAX_CONCURRENCY,
        ),
        ssrf_allow_private_networks=settings.ssrf_allow_private_networks,
        allowed_ports=list(settings.ssrf_allowed_ports),
        access_token_ttl_minutes=settings.access_token_ttl_minutes,
        refresh_token_ttl_days=settings.refresh_token_ttl_days,
    )
