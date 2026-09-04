"""Enumerados del dominio.

Se persisten como `VARCHAR` con `CHECK` (D-006): añadir un valor es una
migración simple y reversible, a diferencia de `ALTER TYPE`.
"""

from __future__ import annotations

from enum import StrEnum

import sqlalchemy as sa


class ScanType(StrEnum):
    FULL = "full"
    SECURITY = "security"
    SEO = "seo"
    PERFORMANCE = "performance"


class ScanStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIAL = "partial"

    @property
    def is_terminal(self) -> bool:
        return self in {
            ScanStatus.COMPLETED,
            ScanStatus.FAILED,
            ScanStatus.CANCELLED,
            ScanStatus.PARTIAL,
        }


class ModuleName(StrEnum):
    DISCOVERY = "discovery"
    CRAWLER = "crawler"
    SECURITY = "security"
    SEO = "seo"
    PERFORMANCE = "performance"
    SEARCH_CONSOLE = "search_console"
    FINDINGS = "findings"
    SCORING = "scoring"
    REPORT = "report"


class ModuleStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class FindingSource(StrEnum):
    ZAP = "zap"
    SEO = "seo"
    CRAWLER = "crawler"
    PAGESPEED = "pagespeed"
    SEARCH_CONSOLE = "search_console"


class FindingCategory(StrEnum):
    SECURITY = "security"
    SEO = "seo"
    PERFORMANCE = "performance"
    ACCESSIBILITY = "accessibility"
    BEST_PRACTICES = "best_practices"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FindingStatus(StrEnum):
    OPEN = "open"
    FIXED = "fixed"
    ACCEPTED = "accepted"
    FALSE_POSITIVE = "false_positive"

    @property
    def penalizes_score(self) -> bool:
        """Solo los findings abiertos afectan el score (scoring.md §3)."""
        return self is FindingStatus.OPEN


class PageSpeedStrategy(StrEnum):
    MOBILE = "mobile"
    DESKTOP = "desktop"


class ConnectionStatus(StrEnum):
    CONNECTED = "connected"
    REVOKED = "revoked"
    ERROR = "error"


class SearchConsolePeriod(StrEnum):
    LAST_7_DAYS = "7d"
    LAST_28_DAYS = "28d"
    LAST_90_DAYS = "90d"

    @property
    def days(self) -> int:
        return {"7d": 7, "28d": 28, "90d": 90}[self.value]


class SearchConsoleDimension(StrEnum):
    DATE = "date"
    QUERY = "query"
    PAGE = "page"
    COUNTRY = "country"
    DEVICE = "device"


class ScoreSystem(StrEnum):
    """Distingue el score propio del de Google (§27, ADR-006)."""

    SOFTREE = "softree"
    GOOGLE = "google"


class ScoreCategory(StrEnum):
    OVERALL = "overall"
    SECURITY = "security"
    PERFORMANCE = "performance"
    SEO = "seo"
    ACCESSIBILITY = "accessibility"
    BEST_PRACTICES = "best_practices"


class ReportFormat(StrEnum):
    PDF = "pdf"
    HTML = "html"
    JSON = "json"


class ReportAudience(StrEnum):
    TECHNICAL = "technical"
    EXECUTIVE = "executive"
    COMBINED = "combined"


def enum_column(enum_cls: type[StrEnum], name: str) -> sa.Enum:
    """Columna de enumerado como VARCHAR con CHECK."""
    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )
