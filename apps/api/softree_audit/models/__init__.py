"""Modelos de dominio.

Importar desde aquí garantiza que todas las tablas queden registradas en
`Base.metadata` antes de que Alembic las compare.
"""

from softree_audit.models.ai import AiAnalysis
from softree_audit.models.enums import (
    Confidence,
    ConnectionStatus,
    FindingCategory,
    FindingSource,
    FindingStatus,
    ModuleName,
    ModuleStatus,
    PageSpeedStrategy,
    ReportAudience,
    ReportFormat,
    ScanStatus,
    ScanType,
    ScoreCategory,
    ScoreSystem,
    SearchConsoleDimension,
    SearchConsolePeriod,
    Severity,
)
from softree_audit.models.finding import Finding
from softree_audit.models.page import Page
from softree_audit.models.project import Project
from softree_audit.models.report import Report
from softree_audit.models.results import PerformanceResult, SEOResult
from softree_audit.models.scan import Scan, ScanModuleRun
from softree_audit.models.score import Score
from softree_audit.models.search_console import SearchConsoleConnection, SearchConsoleMetric
from softree_audit.models.site import Scope, Site
from softree_audit.models.user import RefreshToken, User

__all__ = [
    "AiAnalysis",
    "Confidence",
    "ConnectionStatus",
    "Finding",
    "FindingCategory",
    "FindingSource",
    "FindingStatus",
    "ModuleName",
    "ModuleStatus",
    "Page",
    "PageSpeedStrategy",
    "PerformanceResult",
    "Project",
    "RefreshToken",
    "Report",
    "ReportAudience",
    "ReportFormat",
    "SEOResult",
    "Scan",
    "ScanModuleRun",
    "ScanStatus",
    "ScanType",
    "Scope",
    "Score",
    "ScoreCategory",
    "ScoreSystem",
    "SearchConsoleConnection",
    "SearchConsoleDimension",
    "SearchConsoleMetric",
    "SearchConsolePeriod",
    "Severity",
    "Site",
    "User",
]
