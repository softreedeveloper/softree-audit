"""Deduplicación de findings (§25).

Dos findings equivalentes no deben aparecer repetidos: se conserva el primero y
se acumulan las repeticiones en `occurrences`.
"""

from __future__ import annotations

from collections.abc import Iterable

from softree_audit.services.findings.models import NormalizedFinding


def deduplicate(findings: Iterable[NormalizedFinding]) -> list[NormalizedFinding]:
    """Agrupa por huella conservando el orden de aparición."""
    grouped: dict[str, NormalizedFinding] = {}

    for finding in findings:
        key = finding.fingerprint
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = finding
            continue

        existing.occurrences += finding.occurrences
        # Ante evidencia distinta se conserva la primera y se anota que hay más
        # casos; el detalle completo vive en el conteo de repeticiones.
        if finding.evidence and existing.evidence and finding.evidence not in existing.evidence:
            existing.evidence = f"{existing.evidence}\n…"

    return list(grouped.values())
