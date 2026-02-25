"""Synthetic source trees for the self checks.

Every ``problems()`` in the tools layer comes back empty against the real tree,
which is the point of having them. That leaves the branch that builds the
message never running in a test, so a check whose message is wrong, or whose
detection is broken in a way that produces no output, would pass forever.

These fixtures build a :class:`SourceFile` out of a string. A test then
monkeypatches ``source_files`` or ``suite_files`` in the check's own namespace,
which works because every check imports them at module level.
"""

from __future__ import annotations

import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest

from shearstud.tools.walk import PACKAGE_ROOT, SourceFile


def make_source(relative: str, body: str) -> SourceFile:
    """A source file at a path inside the package, from dedented text."""
    return SourceFile(path=PACKAGE_ROOT / relative, text=textwrap.dedent(body).lstrip())


def make_test(relative: str, body: str) -> SourceFile:
    """A test file, from dedented text."""
    root = PACKAGE_ROOT.parent.parent / "tests"
    return SourceFile(path=root / relative, text=textwrap.dedent(body).lstrip())


@pytest.fixture
def source() -> Callable[[str, str], SourceFile]:
    """Build a package source file."""
    return make_source


@pytest.fixture
def suite() -> Callable[[str, str], SourceFile]:
    """Build a test file."""
    return make_test


@pytest.fixture
def planted(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Point a check's own ``source_files`` at a synthetic tree.

    Patching the name in the check's namespace rather than in ``walk`` is what
    makes this work at all, and it is why every check imports the function
    rather than the module.
    """

    def plant(module: object, files: list[SourceFile], attribute: str = "source_files") -> None:
        def stand_in(include_tools: bool = False) -> list[SourceFile]:
            return files

        monkeypatch.setattr(module, attribute, stand_in)

    return plant


@pytest.fixture
def repo_root() -> Path:
    """Where the checked out repository is."""
    return PACKAGE_ROOT.parent.parent
