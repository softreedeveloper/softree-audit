"""Normalización de alertas de ZAP (ADR-004).

Las alertas crudas nunca se muestran tal cual: pasan por el normalizador y se
convierten en findings del modelo unificado.
"""

from __future__ import annotations

from typing import Any

import pytest
from softree_audit.models.enums import Confidence, FindingCategory, FindingSource, Severity
from softree_audit.services.security.normalizer import (
    extract_cwe,
    extract_owasp,
    extract_references,
    map_confidence,
    map_severity,
    normalize_alerts,
    rule_id_of,
)

pytestmark = pytest.mark.unit


def alert(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "pluginId": "10038",
        "alertRef": "10038-1",
        "name": "Content Security Policy (CSP) Header Not Set",
        "risk": "Medium",
        "confidence": "High",
        "url": "https://softree.mx/",
        "param": "",
        "evidence": "",
        "description": "No se encontró la cabecera CSP.",
        "solution": "Configurar la cabecera Content-Security-Policy.",
        "reference": "https://developer.mozilla.org/docs/Web/HTTP/CSP\nno-es-una-url",
        "cweid": "693",
        "wascid": "15",
        "tags": {
            "OWASP_2021_A05": "https://owasp.org/Top10/A05",
            "CWE-693": "https://cwe.mitre.org",
        },
    }
    return {**defaults, **overrides}


# ── Mapeos ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("risk", "expected"),
    [
        ("High", Severity.HIGH),
        ("Medium", Severity.MEDIUM),
        ("Low", Severity.LOW),
        ("Informational", Severity.INFO),
        ("info", Severity.INFO),
        ("desconocido", Severity.INFO),
        (None, Severity.INFO),
    ],
)
def test_severity_mapping(risk: str | None, expected: Severity) -> None:
    assert map_severity(risk) is expected


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        ("High", Confidence.HIGH),
        ("User Confirmed", Confidence.HIGH),
        ("Medium", Confidence.MEDIUM),
        ("Low", Confidence.LOW),
        ("otra cosa", Confidence.MEDIUM),
    ],
)
def test_confidence_mapping(confidence: str, expected: Confidence) -> None:
    assert map_confidence(confidence) is expected


def test_cwe_extraction() -> None:
    assert extract_cwe(alert()) == "CWE-693"
    assert extract_cwe(alert(cweid="0")) is None
    assert extract_cwe(alert(cweid="-1")) is None
    assert extract_cwe(alert(cweid="")) is None


def test_owasp_extraction_prefers_the_most_recent_edition() -> None:
    tagged = alert(tags={"OWASP_2017_A06": "x", "OWASP_2021_A05": "y"})
    assert extract_owasp(tagged) == "OWASP 2021 A05"


def test_owasp_extraction_without_tags() -> None:
    assert extract_owasp(alert(tags={})) is None
    assert extract_owasp(alert(tags="no es un dict")) is None


def test_references_keep_only_urls() -> None:
    assert extract_references(alert()) == ["https://developer.mozilla.org/docs/Web/HTTP/CSP"]


def test_rule_id_prefers_alert_ref() -> None:
    """`alertRef` distingue variantes de una misma regla."""
    assert rule_id_of(alert()) == "10038-1"
    assert rule_id_of(alert(alertRef="")) == "10038"
    assert rule_id_of({"name": "x"}) == "zap-desconocido"


# ── Normalización ──────────────────────────────────────────────────────────


def test_alert_becomes_a_unified_finding() -> None:
    findings = normalize_alerts([alert()])
    assert len(findings) == 1

    finding = findings[0]
    assert finding.source is FindingSource.ZAP
    assert finding.category is FindingCategory.SECURITY
    assert finding.rule_id == "10038-1"
    assert finding.severity is Severity.MEDIUM
    assert finding.confidence is Confidence.HIGH
    assert finding.cwe == "CWE-693"
    assert finding.owasp == "OWASP 2021 A05"
    assert finding.remediation == "Configurar la cabecera Content-Security-Policy."
    # Con una sola URL el dato es accionable y se conserva.
    assert finding.url == "https://softree.mx/"


def test_raw_alert_is_kept_for_traceability() -> None:
    """Se conserva el original, pero nunca se presenta sin normalizar."""
    finding = normalize_alerts([alert()])[0]
    assert finding.raw is not None
    assert finding.raw["zap_alert"]["pluginId"] == "10038"


def test_same_rule_on_many_urls_is_one_finding() -> None:
    """Una cabecera ausente en 3 páginas es un problema de servidor, no tres."""
    alerts = [alert(url=f"https://softree.mx/pagina-{index}") for index in range(3)]
    findings = normalize_alerts(alerts)

    assert len(findings) == 1
    assert findings[0].occurrences == 3
    assert findings[0].url is None
    evidence = findings[0].evidence or ""
    assert "URL afectadas (3)" in evidence
    assert "https://softree.mx/pagina-0" in evidence


def test_different_parameters_are_different_findings() -> None:
    alerts = [
        alert(name="XSS reflejado", param="q", url="https://softree.mx/buscar"),
        alert(name="XSS reflejado", param="orden", url="https://softree.mx/buscar"),
    ]
    assert len(normalize_alerts(alerts)) == 2


def test_different_rules_are_different_findings() -> None:
    alerts = [alert(alertRef="10038-1"), alert(alertRef="10020-1", name="Otra")]
    assert len(normalize_alerts(alerts)) == 2


@pytest.mark.security
def test_alerts_marked_false_positive_by_zap_are_discarded() -> None:
    """Incorporarlas sería ruido que ZAP ya descartó."""
    alerts = [alert(confidence="False Positive"), alert(alertRef="10020-1", name="Real")]
    findings = normalize_alerts(alerts)
    assert [finding.rule_id for finding in findings] == ["10020-1"]


def test_findings_are_ordered_by_severity_then_reach() -> None:
    alerts = [
        alert(alertRef="a", risk="Low", name="Baja"),
        alert(alertRef="b", risk="High", name="Alta"),
        alert(alertRef="c", risk="Medium", name="Media"),
    ]
    assert [f.severity for f in normalize_alerts(alerts)] == [
        Severity.HIGH,
        Severity.MEDIUM,
        Severity.LOW,
    ]


def test_within_a_severity_the_widest_reach_comes_first() -> None:
    alerts = [
        alert(alertRef="a", name="Una URL", url="https://softree.mx/x"),
        *[
            alert(alertRef="b", name="Muchas URL", url=f"https://softree.mx/{index}")
            for index in range(4)
        ],
    ]
    findings = normalize_alerts(alerts)
    assert findings[0].occurrences == 4


def test_alert_without_optional_fields_does_not_break() -> None:
    findings = normalize_alerts([{"name": "Mínima", "risk": "Low", "url": "https://x.test/"}])
    assert len(findings) == 1
    assert findings[0].title == "Mínima"
    assert findings[0].cwe is None
    assert findings[0].description


def test_alert_without_name_gets_a_placeholder() -> None:
    findings = normalize_alerts([{"risk": "Low", "url": "https://x.test/"}])
    assert findings[0].title == "Alerta de seguridad sin nombre"


def test_empty_input_produces_nothing() -> None:
    assert normalize_alerts([]) == []


def test_fingerprints_are_unique_within_a_scan() -> None:
    alerts = [
        alert(alertRef="10038-1", param=""),
        alert(alertRef="10038-1", param="q"),
        alert(alertRef="10020-1", param=""),
    ]
    findings = normalize_alerts(alerts)
    assert len({finding.fingerprint for finding in findings}) == len(findings)
