"""Regla de dependencias entre capas (`docs/spec/architecture.md` §2).

`packages/scoring` debe permanecer puro: sin acceso a base de datos, red ni
framework web. Los `services/*` no deben importar la capa de API.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
import softree_audit

pytestmark = pytest.mark.unit

PACKAGE_ROOT = pathlib.Path(softree_audit.__file__).parent

FORBIDDEN_IN_SCORING = ("softree_audit.db", "softree_audit.api", "sqlalchemy", "httpx", "fastapi")
FORBIDDEN_IN_SERVICES = ("softree_audit.api", "fastapi")


def _imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _violations(subpackage: str, forbidden: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for path in (PACKAGE_ROOT / subpackage).rglob("*.py"):
        for module in _imported_modules(path):
            if any(module == item or module.startswith(f"{item}.") for item in forbidden):
                found.append(f"{path.relative_to(PACKAGE_ROOT)} importa {module}")
    return found


def test_scoring_package_stays_pure() -> None:
    assert _violations("scoring", FORBIDDEN_IN_SCORING) == []


def test_services_do_not_import_the_api_layer() -> None:
    assert _violations("services", FORBIDDEN_IN_SERVICES) == []
