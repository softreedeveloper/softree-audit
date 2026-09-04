"""Esquemas de proyectos."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from pydantic import Field

from softree_audit.schemas.common import ApiModel

NAME_MAX_LENGTH = 120
CLIENT_NAME_MAX_LENGTH = 160
NOTES_MAX_LENGTH = 4000

Name = Annotated[str, Field(min_length=1, max_length=NAME_MAX_LENGTH)]
ClientName = Annotated[str | None, Field(default=None, max_length=CLIENT_NAME_MAX_LENGTH)]
Notes = Annotated[str | None, Field(default=None, max_length=NOTES_MAX_LENGTH)]


class ProjectCreate(ApiModel):
    name: Name
    client_name: ClientName = None
    notes: Notes = None


class ProjectUpdate(ApiModel):
    name: Name
    client_name: ClientName = None
    notes: Notes = None


class ProjectRead(ApiModel):
    id: uuid.UUID
    name: str
    client_name: str | None
    notes: str | None
    sites_count: int = Field(default=0, description="Número de sitios del proyecto.")
    created_at: dt.datetime
    updated_at: dt.datetime
