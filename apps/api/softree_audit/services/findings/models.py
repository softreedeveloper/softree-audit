"""Finding normalizado y su huella de deduplicación."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from softree_audit.models.enums import (
    Confidence,
    FindingCategory,
    FindingSource,
    Severity,
)

MAX_EVIDENCE_LENGTH = 4000


def _canonical_url(url: str | None) -> str:
    """Forma estable de una URL para la huella.

    Sin fragmento y sin barra final, de modo que `/a`, `/a/` y `/a#x` produzcan
    la misma huella y no generen findings repetidos.
    """
    if not url:
        return ""
    parts = urlsplit(url)._replace(fragment="")
    path = parts.path.rstrip("/") or "/"
    return parts._replace(path=path).geturl().lower()


def build_fingerprint(
    *,
    source: FindingSource,
    rule_id: str | None,
    category: FindingCategory,
    url: str | None,
    parameter: str | None,
) -> str:
    """Huella de deduplicación (§25).

    Se calcula sobre fuente, regla o categoría, URL y parámetro. Es estable
    entre scans del mismo sitio, lo que permitirá arrastrar los estados
    `accepted` y `false_positive` en el Slice 8.
    """
    material = "|".join(
        [
            source.value,
            rule_id or category.value,
            _canonical_url(url),
            (parameter or "").strip().lower(),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class NormalizedFinding:
    """Finding en el formato unificado de `docs/spec/database.md` §findings."""

    source: FindingSource
    category: FindingCategory
    title: str
    severity: Severity
    description: str
    confidence: Confidence = Confidence.HIGH
    rule_id: str | None = None
    url: str | None = None
    parameter: str | None = None
    evidence: str | None = None
    impact: str | None = None
    remediation: str | None = None
    client_explanation: str | None = None
    cwe: str | None = None
    owasp: str | None = None
    references: list[Any] = field(default_factory=list)
    occurrences: int = 1
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.evidence and len(self.evidence) > MAX_EVIDENCE_LENGTH:
            self.evidence = self.evidence[: MAX_EVIDENCE_LENGTH - 1] + "…"

    @property
    def fingerprint(self) -> str:
        return build_fingerprint(
            source=self.source,
            rule_id=self.rule_id,
            category=self.category,
            url=self.url,
            parameter=self.parameter,
        )
