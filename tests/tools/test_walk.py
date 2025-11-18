"""The source walker the self checks are built on."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from shearstud.errors import ConfigError
from shearstud.tools import walk
from shearstud.tools.walk import SourceFile

pytestmark = pytest.mark.tools


def test_the_package_root_holds_the_package() -> None:
    assert (walk.PACKAGE_ROOT / "errors.py").exists()
    assert walk.PACKAGE_ROOT.name == "shearstud"


def test_the_repo_root_holds_the_tests(repo_root: Path) -> None:
    assert (repo_root / "tests").is_dir()
    assert (repo_root / "pyproject.toml").exists()


def test_the_walker_finds_the_application_source() -> None:
    names = {source.name for source in walk.source_files()}
    assert "src/shearstud/errors.py" in names
    assert "src/shearstud/geometry/section.py" in names


def test_the_tools_are_left_out_by_default() -> None:
    names = {source.name for source in walk.source_files()}
    assert not any("tools/" in name for name in names)


def test_the_tools_can_be_asked_for() -> None:
    names = {source.name for source in walk.source_files(include_tools=True)}
    assert any("tools/walk.py" in name for name in names)


def test_the_data_directory_is_never_walked() -> None:
    names = {source.name for source in walk.source_files(include_tools=True)}
    assert not any("/data/" in name for name in names)


def test_the_files_come_back_in_path_order() -> None:
    names = [source.name for source in walk.source_files()]
    assert names == sorted(names)


def test_the_suite_is_found() -> None:
    names = {source.name for source in walk.suite_files()}
    assert any(name.endswith("test_section.py") for name in names)


def test_every_suite_file_is_a_test_file() -> None:
    for source in walk.suite_files():
        assert Path(source.name).name.startswith("test_")


def test_a_missing_suite_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(walk, "TESTS_ROOT", tmp_path / "gone")
    with pytest.raises(ConfigError, match="no test suite"):
        walk.suite_files()


def test_a_source_file_reports_its_module(source: Callable[[str, str], SourceFile]) -> None:
    assert source("geometry/section.py", "x = 1").module == "shearstud.geometry.section"


def test_a_package_init_drops_its_last_part(source: Callable[[str, str], SourceFile]) -> None:
    assert source("geometry/__init__.py", "x = 1").module == "shearstud.geometry"


def test_a_source_file_reports_its_layer(source: Callable[[str, str], SourceFile]) -> None:
    assert source("geometry/section.py", "x = 1").layer == "geometry"
    assert source("errors.py", "x = 1").layer == ""


def test_a_source_file_parses_once(source: Callable[[str, str], SourceFile]) -> None:
    file = source("x.py", "def f() -> None:\n    pass\n")
    assert file.tree is file.tree


def test_a_file_that_does_not_parse_is_reported(
    source: Callable[[str, str], SourceFile],
) -> None:
    file = source("bad.py", "def (:\n")
    with pytest.raises(ConfigError):
        _ = file.tree


def test_lines_can_be_read_by_number(source: Callable[[str, str], SourceFile]) -> None:
    file = source("x.py", "first\nsecond\nthird\n")
    assert file.line_at(2) == "second"
    assert file.line_at(0) == ""
    assert file.line_at(99) == ""


def test_public_functions_leave_out_the_private_ones(
    source: Callable[[str, str], SourceFile],
) -> None:
    file = source(
        "x.py",
        """
        def public() -> None: ...
        def _private() -> None: ...
        """,
    )
    assert [node.name for node in walk.public_functions(file)] == ["public"]


def test_public_classes_leave_out_the_private_ones(
    source: Callable[[str, str], SourceFile],
) -> None:
    file = source(
        "x.py",
        """
        class Public: ...
        class _Private: ...
        """,
    )
    assert [node.name for node in walk.public_classes(file)] == ["Public"]


def test_public_methods_leave_out_the_dunder_ones(
    source: Callable[[str, str], SourceFile],
) -> None:
    file = source(
        "x.py",
        """
        class Thing:
            def visible(self) -> None: ...
            def _hidden(self) -> None: ...
            def __len__(self) -> int: ...
        """,
    )
    node = walk.public_classes(file)[0]
    assert [m.name for m in walk.public_methods(node)] == ["visible"]


def test_imported_modules_finds_a_from_import(
    source: Callable[[str, str], SourceFile],
) -> None:
    file = source("x.py", "from shearstud.geometry.section import Section\nimport os\n")
    assert walk.imported_modules(file) == {"shearstud.geometry.section"}


def test_imported_modules_finds_a_plain_import(
    source: Callable[[str, str], SourceFile],
) -> None:
    file = source("x.py", "import shearstud.units\n")
    assert walk.imported_modules(file) == {"shearstud.units"}


def test_imported_modules_ignores_the_standard_library(
    source: Callable[[str, str], SourceFile],
) -> None:
    file = source("x.py", "import math\nfrom pathlib import Path\n")
    assert walk.imported_modules(file) == set()


def test_a_clean_report_says_so(capsys: pytest.CaptureFixture[str]) -> None:
    code = walk.report("check_thing", [])
    assert code == 0
    assert "check_thing: clean" in capsys.readouterr().out


def test_a_report_with_problems_prints_them_all(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = walk.report("check_thing", ["first is wrong", "second is wrong"])
    out = capsys.readouterr().out
    assert code == 1
    assert "first is wrong" in out
    assert "second is wrong" in out
    assert "2 problem(s)" in out
