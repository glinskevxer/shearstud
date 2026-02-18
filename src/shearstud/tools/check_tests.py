"""Every module has a test file, every test file has a marker, every test asserts.

Coverage says which lines ran. This says which modules anybody thought about,
which is a different and cruder question, and the two disagree in the direction
that matters: a module can be at ninety percent line coverage entirely by
accident, imported and exercised by somebody else's test, with nothing anywhere
that says what it is supposed to do.

The third rule is the one that catches the worst thing. A test function with no
assertion in it passes whatever the code does, and a suite full of them is worse
than no suite because it reports a number.
"""

from __future__ import annotations

import ast
import sys
from typing import Final

from shearstud.tools.walk import (
    PACKAGE_ROOT,
    SourceFile,
    report,
    source_files,
    suite_files,
)

#: Modules that do not need a test file of their own.
EXEMPT_MODULES: Final[frozenset[str]] = frozenset(
    {
        "shearstud",
        "shearstud.geometry",
        "shearstud.loads",
        "shearstud.signals",
        "shearstud.fatigue",
        "shearstud.structure",
        "shearstud.rating",
        "shearstud.store",
        "shearstud.store.migrations",
        "shearstud.program",
        "shearstud.analysis",
        "shearstud.cli",
        "shearstud.tools",
    }
)

#: Test file names that do not follow the module they cover.
ALIASES: Final[dict[str, str]] = {
    "shearstud.cli.main": "test_cli_main.py",
    "shearstud.cli.structures": "test_cli_structures.py",
    "shearstud.cli.rating": "test_cli_rating.py",
    "shearstud.cli.measurement": "test_cli_measurement.py",
    "shearstud.store.migrations.m001_structures": "test_migrate.py",
    "shearstud.store.migrations.m002_measurement": "test_migrate.py",
    "shearstud.store.migrations.m003_assessment": "test_migrate.py",
}


def _expected_name(module: str) -> str:
    """Which test file a module's tests live in."""
    if module in ALIASES:
        return ALIASES[module]
    return f"test_{module.rsplit('.', 1)[-1]}.py"


def _asserts(node: ast.FunctionDef) -> bool:
    """True when a test function asserts something or expects a raise."""
    for inner in ast.walk(node):
        if isinstance(inner, ast.Assert):
            return True
        if isinstance(inner, ast.withitem):
            call = inner.context_expr
            if isinstance(call, ast.Call) and "raises" in ast.dump(call.func):
                return True
    return False


def _test_functions(source: SourceFile) -> list[ast.FunctionDef]:
    return [
        node
        for node in source.tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


def _has_marker(source: SourceFile) -> bool:
    for node in source.tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "pytestmark":
                    return True
    return False


def problems() -> list[str]:
    """Modules with no tests, files with no marker, tests with no assertion."""
    found: list[str] = []
    suite = suite_files()
    names = {source.path.name for source in suite}

    for source in source_files(include_tools=True):
        module = source.module
        if module in EXEMPT_MODULES:
            continue
        expected = _expected_name(module)
        if expected not in names:
            found.append(f"{source.name} has no {expected}")

    for source in suite:
        if not _has_marker(source):
            found.append(f"{source.name} sets no pytestmark")
        functions = _test_functions(source)
        if not functions:
            found.append(f"{source.name} holds no tests")
        for node in functions:
            if not _asserts(node):
                found.append(f"{source.name}:{node.lineno} {node.name} asserts nothing")
    return found


def module_names() -> list[str]:
    """Every module the check expects a test file for."""
    return sorted(
        source.module
        for source in source_files(include_tools=True)
        if source.module not in EXEMPT_MODULES
    )


def main() -> int:
    """Run the check and report."""
    if not PACKAGE_ROOT.exists():  # pragma: no cover - defensive
        return report("check_tests", [f"no package at {PACKAGE_ROOT}"])
    return report("check_tests", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
