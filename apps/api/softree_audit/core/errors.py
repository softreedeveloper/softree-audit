"""Errores de dominio y su traducción a respuestas HTTP.

Formato único de error, documentado en `docs/spec/api.md`:

    {"error": {"code": "...", "message": "...", "details": null}}
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Error de aplicación con código estable y mensaje presentable."""

    status_code: int = 400
    code: str = "bad_request"
    message: str = "Petición inválida."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Any = None,
        status_code: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        self.status_code = status_code or self.status_code
        self.headers = headers or {}
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthenticated"
    message = "Autenticación requerida."


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"
    message = "Email o contraseña incorrectos."


class InactiveUserError(AuthenticationError):
    code = "inactive_user"
    message = "La cuenta está desactivada."


class InvalidTokenError(AuthenticationError):
    code = "invalid_token"
    message = "Token inválido o expirado."


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"
    message = "No tiene permiso para realizar esta operación."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Recurso no encontrado."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "El estado actual del recurso no permite esta operación."


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Demasiadas peticiones. Intente más tarde."

    def __init__(self, retry_after_seconds: int, **kwargs: Any) -> None:
        super().__init__(headers={"Retry-After": str(retry_after_seconds)}, **kwargs)
        self.retry_after_seconds = retry_after_seconds


class ExternalServiceError(AppError):
    status_code = 502
    code = "external_service_error"
    message = "Una integración externa no respondió correctamente."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "Servicio temporalmente no disponible."
