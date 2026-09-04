"""Router de la versión 1 de la API."""

from __future__ import annotations

from fastapi import APIRouter

from softree_audit.api.v1 import (
    auth,
    dashboard,
    findings,
    health,
    integrations,
    projects,
    reports,
    scans,
    sites,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(dashboard.router)
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(sites.router)
api_router.include_router(scans.router)
api_router.include_router(findings.router)
api_router.include_router(integrations.router)
api_router.include_router(reports.router)
