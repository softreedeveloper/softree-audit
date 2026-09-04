"""Normalizador de alertas de ZAP.

Las alertas crudas nunca se presentan como findings finales (ADR-004):

    ZAP Alert → Finding Normalizer → Softree Finding

Las alertas se agrupan por regla y parámetro. Una cabecera de seguridad ausente
en dieciocho páginas es un solo problema de configuración del servidor, no
dieciocho hallazgos: se reporta una vez, con las URL afectadas en la evidencia
y el número de casos en `occurrences`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from softree_audit.models.enums import (
    Confidence,
    FindingCategory,
    FindingSource,
    Severity,
)
from softree_audit.services.findings.models import NormalizedFinding

# ZAP clasifica el riesgo en cuatro niveles; no emite «critical» en passive scan.
RISK_TO_SEVERITY: dict[str, Severity] = {
    "high": Severity.HIGH,
    "medium": Severity.MEDIUM,
    "low": Severity.LOW,
    "informational": Severity.INFO,
    "info": Severity.INFO,
}

CONFIDENCE_MAP: dict[str, Confidence] = {
    "high": Confidence.HIGH,
    "user confirmed": Confidence.HIGH,
    "medium": Confidence.MEDIUM,
    "low": Confidence.LOW,
}

# ZAP marca así las alertas que él mismo considera falsas.
FALSE_POSITIVE_CONFIDENCE = "false positive"

MAX_EVIDENCE_URLS = 20
MAX_TEXT = 3000

_OWASP_TAG = re.compile(r"OWASP[_-](\d{4})[_-](A\d+)", re.IGNORECASE)


def _text(value: Any, limit: int = MAX_TEXT) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


def map_severity(risk: str | None) -> Severity:
    return RISK_TO_SEVERITY.get((risk or "").strip().lower(), Severity.INFO)


def map_confidence(confidence: str | None) -> Confidence:
    return CONFIDENCE_MAP.get((confidence or "").strip().lower(), Confidence.MEDIUM)


def is_false_positive(alert: dict[str, Any]) -> bool:
    return str(alert.get("confidence", "")).strip().lower() == FALSE_POSITIVE_CONFIDENCE


def extract_cwe(alert: dict[str, Any]) -> str | None:
    raw = str(alert.get("cweid", "")).strip()
    if not raw or raw in {"0", "-1"}:
        return None
    return f"CWE-{raw}"


def extract_owasp(alert: dict[str, Any]) -> str | None:
    """Categoría OWASP a partir de las etiquetas de la alerta."""
    tags = alert.get("tags")
    if not isinstance(tags, dict):
        return None

    matches: list[str] = []
    for key in tags:
        found = _OWASP_TAG.search(str(key))
        if found:
            matches.append(f"OWASP {found.group(1)} {found.group(2).upper()}")
    if not matches:
        return None
    # La más reciente primero, que es la referencia útil hoy.
    return sorted(set(matches), reverse=True)[0]


def extract_references(alert: dict[str, Any]) -> list[str]:
    raw = _text(alert.get("reference"), 2000)
    if not raw:
        return []
    return [line.strip() for line in raw.splitlines() if line.strip().startswith("http")][:10]


def rule_id_of(alert: dict[str, Any]) -> str:
    """`alertRef` distingue variantes de una misma regla; si falta, el pluginId."""
    return str(alert.get("alertRef") or alert.get("pluginId") or "zap-desconocido").strip()


def _group_key(alert: dict[str, Any]) -> tuple[str, str, str]:
    return (
        rule_id_of(alert),
        str(alert.get("param") or "").strip(),
        str(alert.get("risk") or "").strip().lower(),
    )


def normalize_alerts(alerts: list[dict[str, Any]]) -> list[NormalizedFinding]:
    """Convierte alertas crudas de ZAP en findings del modelo unificado."""
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)

    for alert in alerts:
        if is_false_positive(alert):
            # ZAP ya la descartó; incorporarla sería ruido conocido.
            continue
        groups[_group_key(alert)].append(alert)

    findings: list[NormalizedFinding] = []
    for group in groups.values():
        findings.append(_build_finding(group))

    # Primero lo más grave, y dentro de cada nivel lo que más páginas afecta.
    order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
        Severity.INFO: 4,
    }
    findings.sort(key=lambda item: (order[item.severity], -item.occurrences))
    return findings


def _build_finding(group: list[dict[str, Any]]) -> NormalizedFinding:
    first = group[0]
    urls = []
    for alert in group:
        url = _text(alert.get("url"), 2048)
        if url and url not in urls:
            urls.append(url)

    evidence_lines: list[str] = []
    sample_evidence = next(
        (_text(alert.get("evidence"), 500) for alert in group if alert.get("evidence")), None
    )
    if sample_evidence:
        evidence_lines.append(f"Evidencia: {sample_evidence}")
    attack = _text(first.get("attack"), 500)
    if attack:
        evidence_lines.append(f"Petición: {attack}")
    if urls:
        shown = urls[:MAX_EVIDENCE_URLS]
        evidence_lines.append(f"URL afectadas ({len(urls)}):")
        evidence_lines.extend(shown)
        if len(urls) > len(shown):
            evidence_lines.append(f"… y {len(urls) - len(shown)} más")

    return NormalizedFinding(
        source=FindingSource.ZAP,
        category=FindingCategory.SECURITY,
        rule_id=rule_id_of(first),
        title=_text(first.get("name"), 300) or "Alerta de seguridad sin nombre",
        severity=map_severity(first.get("risk")),
        confidence=map_confidence(first.get("confidence")),
        # Con una sola URL el dato es accionable; con varias, el problema es del
        # servidor y la lista completa vive en la evidencia.
        url=urls[0] if len(urls) == 1 else None,
        parameter=_text(first.get("param"), 200),
        evidence="\n".join(evidence_lines) or None,
        description=_text(first.get("description")) or "Sin descripción proporcionada por ZAP.",
        impact=_text(first.get("other")),
        remediation=_text(first.get("solution")),
        cwe=extract_cwe(first),
        owasp=extract_owasp(first),
        references=list(extract_references(first)),
        occurrences=len(urls) or len(group),
        # Se conserva la alerta original solo para trazabilidad (ADR-004).
        raw={"zap_alert": first},
    )
