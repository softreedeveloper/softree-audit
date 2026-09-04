"""Esquemas de sitios auditados."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from pydantic import Field, field_validator, model_validator

from softree_audit.schemas.common import ApiModel
from softree_audit.schemas.scope import ScopeRead
from softree_audit.services.common.urls import InvalidUrlError, normalize_url

NAME_MAX_LENGTH = 120
AUTHORIZED_BY_MAX_LENGTH = 200
AUTHORIZATION_NOTES_MAX_LENGTH = 2000

Name = Annotated[str, Field(min_length=1, max_length=NAME_MAX_LENGTH)]


class SiteBase(ApiModel):
    name: Name
    base_url: Annotated[str, Field(min_length=8, max_length=2048)]
    authorized_by: Annotated[
        str | None, Field(default=None, max_length=AUTHORIZED_BY_MAX_LENGTH)
    ] = None
    authorization_date: dt.date | None = None
    authorization_notes: Annotated[
        str | None, Field(default=None, max_length=AUTHORIZATION_NOTES_MAX_LENGTH)
    ] = None
    is_active: bool = True

    @field_validator("base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        try:
            return normalize_url(value)
        except InvalidUrlError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def _check_authorization(self) -> SiteBase:
        """La autorización es todo o nada.

        Un sitio con quién autorizó pero sin fecha, o al revés, dejaría un
        registro de autorización incompleto y no auditable (`security.md` §1).
        """
        if bool(self.authorized_by) != (self.authorization_date is not None):
            raise ValueError(
                "authorized_by y authorization_date deben informarse juntos o dejarse vacíos"
            )
        today = dt.datetime.now(dt.UTC).date()
        if self.authorization_date and self.authorization_date > today:
            raise ValueError("La fecha de autorización no puede ser futura")
        return self


class SiteCreate(SiteBase):
    project_id: uuid.UUID


class SiteUpdate(SiteBase):
    pass


class SiteRead(ApiModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    base_url: str
    authorized_by: str | None
    authorization_date: dt.date | None
    authorization_notes: str | None
    is_active: bool
    is_authorized: bool = Field(
        description="Si el sitio puede escanearse. Requiere autorización registrada."
    )
    scans_count: int = 0
    created_at: dt.datetime
    updated_at: dt.datetime


class SiteDetail(SiteRead):
    scope: ScopeRead
