"""Invariantes de los enumerados del dominio."""

from __future__ import annotations

import pytest
from softree_audit.models.enums import (
    FindingStatus,
    ScanStatus,
    ScoreSystem,
    SearchConsolePeriod,
)

pytestmark = pytest.mark.unit


def test_scan_terminal_states() -> None:
    """`docs/spec/architecture.md` §4."""
    terminal = {status for status in ScanStatus if status.is_terminal}
    assert terminal == {
        ScanStatus.COMPLETED,
        ScanStatus.FAILED,
        ScanStatus.CANCELLED,
        ScanStatus.PARTIAL,
    }
    assert ScanStatus.QUEUED.is_terminal is False
    assert ScanStatus.RUNNING.is_terminal is False


def test_only_open_findings_penalize_the_score() -> None:
    """`docs/spec/scoring.md` §3."""
    assert FindingStatus.OPEN.penalizes_score is True
    for status in (FindingStatus.FIXED, FindingStatus.ACCEPTED, FindingStatus.FALSE_POSITIVE):
        assert status.penalizes_score is False


def test_search_console_periods() -> None:
    assert SearchConsolePeriod.LAST_7_DAYS.days == 7
    assert SearchConsolePeriod.LAST_28_DAYS.days == 28
    assert SearchConsolePeriod.LAST_90_DAYS.days == 90


def test_two_score_systems_exist_and_are_distinct() -> None:
    """Requisito §27: el score propio nunca se presenta como score de Google."""
    assert {system.value for system in ScoreSystem} == {"softree", "google"}
