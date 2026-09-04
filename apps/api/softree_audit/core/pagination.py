"""Paginación por cursor.

El cursor es opaco para el cliente: codifica el identificador del último
elemento devuelto. Como los identificadores son UUID v7, ordenables por tiempo
de creación, basta con comparar por `id` para obtener una paginación estable
frente a inserciones concurrentes (ADR-002).
"""

from __future__ import annotations

import base64
import binascii
import uuid

from softree_audit.core.errors import AppError

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


class InvalidCursorError(AppError):
    status_code = 400
    code = "invalid_cursor"
    message = "El cursor de paginación no es válido."


def encode_cursor(last_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(last_id.bytes).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> uuid.UUID:
    padding = "=" * (-len(cursor) % 4)
    try:
        return uuid.UUID(bytes=base64.urlsafe_b64decode(cursor + padding))
    except (binascii.Error, ValueError) as exc:
        raise InvalidCursorError() from exc
