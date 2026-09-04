"""Comparación entre dos auditorías (§32).

Clasifica cada hallazgo respecto al scan anterior y calcula los deltas de las
métricas. Es una función pura: recibe los datos ya leídos y no consulta nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ChangeKind(StrEnum):
    NEW = "new"
    FIXED = "fixed"
    UNCHANGED = "unchanged"
    REGRESSED = "regressed"


# Orden de severidad, de más a menos grave, para saber si algo empeoró.
SEVERITY_RANK: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


@dataclass(frozen=True, slots=True)
class FindingSnapshot:
    """Lo mínimo de un hallazgo para poder compararlo."""

    fingerprint: str
    rule_id: str | None
    title: str
    severity: str
    category: str
    occurrences: int
    source: str = ""
    url: str | None = None
    is_open: bool = True


@dataclass(slots=True)
class FindingChange:
    kind: ChangeKind
    fingerprint: str
    rule_id: str | None
    title: str
    severity: str
    category: str
    url: str | None
    previous_severity: str | None = None
    previous_occurrences: int | None = None
    occurrences: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "fingerprint": self.fingerprint,
            "rule_id": self.rule_id,
            "title": self.title,
            "severity": self.severity,
            "category": self.category,
            "url": self.url,
            "previous_severity": self.previous_severity,
            "occurrences": self.occurrences,
            "previous_occurrences": self.previous_occurrences,
        }


@dataclass(slots=True)
class MetricDelta:
    key: str
    label: str
    previous: float | None
    current: float | None
    # `True` si un valor más alto es mejor (puntuaciones); `False` si es peor
    # (número de errores, tiempos de carga).
    higher_is_better: bool
    unit: str = ""

    @property
    def delta(self) -> float | None:
        if self.previous is None or self.current is None:
            return None
        return round(self.current - self.previous, 3)

    @property
    def direction(self) -> str:
        """`mejora`, `empeora`, `igual` o `desconocido`."""
        change = self.delta
        if change is None:
            return "desconocido"
        if change == 0:
            return "igual"
        improved = change > 0 if self.higher_is_better else change < 0
        return "mejora" if improved else "empeora"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "previous": self.previous,
            "current": self.current,
            "delta": self.delta,
            "direction": self.direction,
            "unit": self.unit,
            "higher_is_better": self.higher_is_better,
        }


@dataclass(slots=True)
class Comparison:
    changes: list[FindingChange] = field(default_factory=list)
    metrics: list[MetricDelta] = field(default_factory=list)
    # Fuentes que midieron las dos auditorías, y las que solo midió una.
    compared_sources: list[str] = field(default_factory=list)
    sources_only_in_current: list[str] = field(default_factory=list)
    sources_only_in_previous: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        totals = dict.fromkeys((kind.value for kind in ChangeKind), 0)
        for change in self.changes:
            totals[change.kind.value] += 1
        return totals

    def as_dict(self) -> dict[str, Any]:
        return {
            "counts": self.counts(),
            "changes": [change.as_dict() for change in self.changes],
            "metrics": [metric.as_dict() for metric in self.metrics],
            "compared_sources": sorted(self.compared_sources),
            "sources_only_in_current": sorted(self.sources_only_in_current),
            "sources_only_in_previous": sorted(self.sources_only_in_previous),
        }


def compare_findings(
    previous: list[FindingSnapshot],
    current: list[FindingSnapshot],
    *,
    comparable_sources: set[str] | None = None,
) -> list[FindingChange]:
    """Clasifica los hallazgos en NEW, FIXED, UNCHANGED y REGRESSED.

    Solo se comparan los hallazgos abiertos: uno aceptado o marcado como falso
    positivo no debe aparecer como corregido ni como nuevo.

    `comparable_sources` acota la comparación a las fuentes que midieron **las
    dos** auditorías. Sin este filtro, comparar un scan SEO con uno completo
    reportaría todos los hallazgos de seguridad como corregidos, cuando lo único
    que ocurrió es que ese módulo no se ejecutó.
    """

    def usable(item: FindingSnapshot) -> bool:
        if not item.is_open:
            return False
        return comparable_sources is None or item.source in comparable_sources

    before = {item.fingerprint: item for item in previous if usable(item)}
    after = {item.fingerprint: item for item in current if usable(item)}

    changes: list[FindingChange] = []

    for fingerprint, item in after.items():
        earlier = before.get(fingerprint)
        if earlier is None:
            changes.append(
                FindingChange(
                    kind=ChangeKind.NEW,
                    fingerprint=fingerprint,
                    rule_id=item.rule_id,
                    title=item.title,
                    severity=item.severity,
                    category=item.category,
                    url=item.url,
                    occurrences=item.occurrences,
                )
            )
            continue

        worse_severity = SEVERITY_RANK.get(item.severity, 9) < SEVERITY_RANK.get(
            earlier.severity, 9
        )
        more_cases = item.occurrences > earlier.occurrences
        kind = ChangeKind.REGRESSED if (worse_severity or more_cases) else ChangeKind.UNCHANGED

        changes.append(
            FindingChange(
                kind=kind,
                fingerprint=fingerprint,
                rule_id=item.rule_id,
                title=item.title,
                severity=item.severity,
                category=item.category,
                url=item.url,
                previous_severity=earlier.severity,
                previous_occurrences=earlier.occurrences,
                occurrences=item.occurrences,
            )
        )

    for fingerprint, item in before.items():
        if fingerprint in after:
            continue
        changes.append(
            FindingChange(
                kind=ChangeKind.FIXED,
                fingerprint=fingerprint,
                rule_id=item.rule_id,
                title=item.title,
                severity=item.severity,
                category=item.category,
                url=item.url,
                previous_occurrences=item.occurrences,
                occurrences=0,
            )
        )

    order = {
        ChangeKind.REGRESSED: 0,
        ChangeKind.NEW: 1,
        ChangeKind.FIXED: 2,
        ChangeKind.UNCHANGED: 3,
    }
    changes.sort(key=lambda item: (order[item.kind], SEVERITY_RANK.get(item.severity, 9)))
    return changes


# Métricas que se comparan, con su etiqueta y su sentido.
METRIC_SPECS: tuple[tuple[str, str, bool, str], ...] = (
    ("softree_overall", "Softree Score", True, ""),
    ("security_score", "Score de seguridad", True, ""),
    ("seo_score", "Score SEO", True, ""),
    ("performance_score", "Score de rendimiento", True, ""),
    ("pages_crawled", "Páginas rastreadas", True, ""),
    ("findings_open", "Hallazgos abiertos", False, ""),
    ("findings_critical", "Hallazgos críticos", False, ""),
    ("findings_high", "Hallazgos altos", False, ""),
    ("broken_internal_links", "Enlaces internos rotos", False, ""),
    ("missing_title", "Páginas sin title", False, ""),
    ("missing_description", "Páginas sin description", False, ""),
    ("missing_h1", "Páginas sin H1", False, ""),
    ("images_missing_alt", "Imágenes sin alt", False, ""),
    ("lcp_ms", "LCP", False, "ms"),
    ("cls", "CLS", False, ""),
    ("tbt_ms", "TBT", False, "ms"),
)


def compare_metrics(
    previous: dict[str, float | None], current: dict[str, float | None]
) -> list[MetricDelta]:
    """Deltas de las métricas presentes en alguno de los dos scans."""
    deltas: list[MetricDelta] = []
    for key, label, higher_is_better, unit in METRIC_SPECS:
        before = previous.get(key)
        after = current.get(key)
        if before is None and after is None:
            continue
        deltas.append(
            MetricDelta(
                key=key,
                label=label,
                previous=before,
                current=after,
                higher_is_better=higher_is_better,
                unit=unit,
            )
        )
    return deltas


def compare(
    *,
    previous_findings: list[FindingSnapshot],
    current_findings: list[FindingSnapshot],
    previous_metrics: dict[str, float | None],
    current_metrics: dict[str, float | None],
    previous_sources: set[str] | None = None,
    current_sources: set[str] | None = None,
) -> Comparison:
    """Compara dos auditorías del mismo sitio.

    Si se indican las fuentes que midió cada una, la comparación se limita a las
    comunes y se declara cuáles quedaron fuera.
    """
    comparable: set[str] | None = None
    only_current: list[str] = []
    only_previous: list[str] = []

    if previous_sources is not None and current_sources is not None:
        comparable = previous_sources & current_sources
        only_current = sorted(current_sources - previous_sources)
        only_previous = sorted(previous_sources - current_sources)

    return Comparison(
        changes=compare_findings(
            previous_findings, current_findings, comparable_sources=comparable
        ),
        metrics=compare_metrics(previous_metrics, current_metrics),
        compared_sources=sorted(comparable) if comparable is not None else [],
        sources_only_in_current=only_current,
        sources_only_in_previous=only_previous,
    )
