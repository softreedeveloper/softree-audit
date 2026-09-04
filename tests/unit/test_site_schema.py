"""Validación de sitios (`schemas/site.py`)."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from pydantic import ValidationError
from softree_audit.schemas.site import SiteCreate

pytestmark = pytest.mark.unit

BASE: dict[str, object] = {
    "project_id": uuid.uuid4(),
    "name": "Sitio corporativo",
    "base_url": "https://softree.mx",
}


def test_base_url_is_normalized() -> None:
    site = SiteCreate(**{**BASE, "base_url": "HTTPS://Softree.mx:443/"})  # type: ignore[arg-type]
    assert site.base_url == "https://softree.mx"


def test_invalid_base_url_is_rejected() -> None:
    with pytest.raises(ValidationError):
        SiteCreate(**{**BASE, "base_url": "ftp://softree.mx"})  # type: ignore[arg-type]


def test_site_without_authorization_is_valid_but_not_scannable() -> None:
    """Se puede registrar un sitio sin autorización; no se podrá auditar."""
    site = SiteCreate(**BASE)  # type: ignore[arg-type]
    assert site.authorized_by is None
    assert site.authorization_date is None


@pytest.mark.security
def test_authorization_fields_must_be_complete() -> None:
    """Media autorización dejaría un registro no auditable (`security.md` §1)."""
    with pytest.raises(ValidationError) as excinfo:
        SiteCreate(**{**BASE, "authorized_by": "Cliente S.A."})  # type: ignore[arg-type]
    assert "authorization_date" in str(excinfo.value)

    with pytest.raises(ValidationError):
        SiteCreate(**{**BASE, "authorization_date": dt.date(2026, 1, 1)})  # type: ignore[arg-type]


@pytest.mark.security
def test_authorization_date_cannot_be_in_the_future() -> None:
    tomorrow = dt.datetime.now(dt.UTC).date() + dt.timedelta(days=1)
    with pytest.raises(ValidationError):
        SiteCreate(  # type: ignore[arg-type]
            **{**BASE, "authorized_by": "Cliente S.A.", "authorization_date": tomorrow}
        )


def test_complete_authorization_is_accepted() -> None:
    site = SiteCreate(  # type: ignore[arg-type]
        **{
            **BASE,
            "authorized_by": "Cliente S.A.",
            "authorization_date": dt.date(2026, 1, 15),
            "authorization_notes": "Contrato 2026-014",
        }
    )
    assert site.authorized_by == "Cliente S.A."
