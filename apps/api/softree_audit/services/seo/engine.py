"""Ejecución del motor SEO.

Una regla que falla no invalida el resto: se registra y se sigue. El motor
devuelve findings ya deduplicados y los agregados del scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from softree_audit.core.logging import get_logger
from softree_audit.services.findings.dedupe import deduplicate
from softree_audit.services.findings.models import NormalizedFinding
from softree_audit.services.seo.aggregates import SeoAggregates, build_aggregates
from softree_audit.services.seo.context import SeoContext
from softree_audit.services.seo.rules import RULES

logger = get_logger(__name__)


@dataclass(slots=True)
class SeoAnalysis:
    findings: list[NormalizedFinding] = field(default_factory=list)
    aggregates: SeoAggregates = field(default_factory=SeoAggregates)
    rules_evaluated: int = 0
    rules_failed: list[str] = field(default_factory=list)
    external_links_checked: int = 0

    def summary(self) -> dict[str, Any]:
        by_rule: dict[str, int] = {}
        for finding in self.findings:
            key = finding.rule_id or "sin_regla"
            by_rule[key] = by_rule.get(key, 0) + 1
        return {
            "findings": len(self.findings),
            "rules_evaluated": self.rules_evaluated,
            "rules_failed": self.rules_failed,
            "external_links_checked": self.external_links_checked,
            "findings_by_rule": by_rule,
            "pages_analyzed": self.aggregates.pages_crawled,
        }


def analyze(context: SeoContext) -> SeoAnalysis:
    analysis = SeoAnalysis(external_links_checked=len(context.external_checks))
    collected: list[NormalizedFinding] = []

    for rule_id, rule in RULES.items():
        try:
            collected.extend(rule(context))
        except Exception as exc:  # una regla rota no invalida el análisis entero
            analysis.rules_failed.append(rule_id)
            logger.warning("seo.rule_failed", rule=rule_id, error=f"{type(exc).__name__}: {exc}")
            continue
        analysis.rules_evaluated += 1

    analysis.findings = deduplicate(collected)
    analysis.aggregates = build_aggregates(context)
    return analysis
