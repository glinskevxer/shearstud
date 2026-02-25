"""Finding and parsing the repository's own source, for the self checks.

Every check in this package works the same way: walk the source, build a list of
problems, print them and exit non zero if there are any. This module is the
walking part, and it exists so that the checks share one idea of what a source
file is and one parsed tree per file rather than twenty.

Two things here are load bearing for the checks' own tests. The files are found
relative to this module rather than to the working directory, so a check gives
the same answer wherever it is run from; and every check imports
:func:`source_files` and :func:`suite_files` into its own namespace at module
level, which is what lets a test point one at a synthetic tree. A check that
reached through ``walk.source_files()`` instead could not be pointed anywhere,
and its problem reporting branch would never run in a test.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from shearstud.errors import ConfigError

#: Root of the installed package.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent

#: Root of the repository, when the package is installed from a checkout.
REPO_ROOT = PACKAGE_ROOT.parent.parent

#: Where the tests live.
TESTS_ROOT = REPO_ROOT / "tests"

#: Directories under the package that are not application code.
EXCLUDED_DIRS = frozenset({"tools", "data", "__pycache__"})


@dataclass(frozen=True)
class SourceFile:
    """One Python file, with its text and its parsed tree.

    Slots are off here, unlike every other frozen dataclass in the package,
    because ``cached_property`` stores its value in the instance dictionary
    and there is not one under slots. Parsing every file once per check run
    rather than once per question is worth the exception.
    """

    path: Path
    text: str

    @cached_property
    def tree(self) -> ast.Module:
        """The parsed module."""
        try:
            return ast.parse(self.text, filename=str(self.path))
        except SyntaxError as exc:
            raise ConfigError(f"{self.path}: {exc}") from exc

    @property
    def name(self) -> str:
        """Path relative to the repository root, with forward slashes."""
        try:
            return self.path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return self.path.as_posix()

    @property
    def module(self) -> str:
        """Dotted module name, for a file inside the package."""
        try:
            relative = self.path.relative_to(PACKAGE_ROOT.parent)
        except ValueError:
            return self.path.stem
        parts = list(relative.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    @property
    def layer(self) -> str:
        """Which package layer the file is in, or an empty string at the top."""
        try:
            relative = self.path.relative_to(PACKAGE_ROOT)
        except ValueError:
            return ""
        return relative.parts[0] if len(relative.parts) > 1 else ""

    def lines(self) -> list[str]:
        """The file's lines, without their endings."""
        return self.text.splitlines()

    def line_at(self, number: int) -> str:
        """One line by its one based number, or an empty string past the end."""
        lines = self.lines()
        if 1 <= number <= len(lines):
            return lines[number - 1]
        return ""


def _read(path: Path) -> SourceFile:
    return SourceFile(path=path, text=path.read_text(encoding="utf-8"))


def source_files(include_tools: bool = False) -> list[SourceFile]:
    """Every application source file, in path order.

    The tools are excluded by default. They are development scaffolding rather
    than application code, and holding them to the same rules as the domain
    layer produces a lot of noise about docstrings on private helpers.
    """
    out: list[SourceFile] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        relative = path.relative_to(PACKAGE_ROOT)
        head = relative.parts[0] if len(relative.parts) > 1 else ""
        if head in EXCLUDED_DIRS and not (include_tools and head == "tools"):
            continue
        out.append(_read(path))
    return out


def suite_files() -> list[SourceFile]:
    """Every test file, in path order."""
    if not TESTS_ROOT.exists():
        raise ConfigError(f"no test suite at {TESTS_ROOT}")
    return [_read(path) for path in sorted(TESTS_ROOT.rglob("test_*.py"))]


def public_functions(source: SourceFile) -> list[ast.FunctionDef]:
    """Top level functions whose names do not start with an underscore."""
    return [
        node
        for node in source.tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    ]


def public_classes(source: SourceFile) -> list[ast.ClassDef]:
    """Top level classes whose names do not start with an underscore."""
    return [
        node
        for node in source.tree.body
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
    ]


def public_methods(node: ast.ClassDef) -> list[ast.FunctionDef]:
    """Methods on a class whose names do not start with an underscore."""
    return [
        item
        for item in node.body
        if isinstance(item, ast.FunctionDef) and not item.name.startswith("_")
    ]


def imported_modules(source: SourceFile) -> set[str]:
    """Every ``shearstud`` module this file imports from."""
    out: set[str] = set()
    for node in ast.walk(source.tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("shearstud"):
                out.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("shearstud"):
                    out.add(alias.name)
    return out


def report(name: str, problems: list[str]) -> int:
    """Print a check's problems and return the exit code it should use."""
    for problem in problems:
        print(f"{name}: {problem}")
    if problems:
        print(f"{name}: {len(problems)} problem(s)")
        return 1
    print(f"{name}: clean")
    return 0
