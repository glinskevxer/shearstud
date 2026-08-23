"""What the wheel carries, and the three things a checkout never exercises."""

from __future__ import annotations

import pytest

from shearstud.tools import check_package as check
from shearstud.tools.walk import PACKAGE_ROOT

pytestmark = pytest.mark.tools


def test_the_package_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_package() -> None:
    assert check.main([]) == 0


def test_the_typing_marker_ships() -> None:
    # Without it a downstream type checker sees this package as untyped and
    # silently loses every annotation in it. Nothing in a checkout notices.
    assert (PACKAGE_ROOT / "py.typed").exists()


def test_the_rolled_catalogue_ships() -> None:
    # Without it every structure built from a catalogue shape fails at import
    # with a file not found, in the wheel and nowhere else.
    assert (PACKAGE_ROOT / "data" / "rolled_shapes.csv").exists()


def test_the_console_script_points_at_the_entry_point() -> None:
    assert check.scripts()[check.SCRIPT_NAME] == check.SCRIPT_TARGET


def test_the_entry_point_is_importable() -> None:
    module_name, _, attribute = check.SCRIPT_TARGET.partition(":")
    import importlib

    module = importlib.import_module(module_name)
    assert callable(getattr(module, attribute))


def test_the_wheel_is_told_which_packages_to_include() -> None:
    assert check.declared_packages() == ["src/shearstud"]


def test_every_layer_is_a_subpackage() -> None:
    found = set(check.subpackages())
    for layer in ("geometry", "loads", "signals", "fatigue", "structure", "rating"):
        assert layer in found, layer
    for layer in ("program", "store", "analysis", "cli", "tools"):
        assert layer in found, layer


def test_a_missing_required_file_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "REQUIRED_FILES", {"nowhere.txt": "because it is needed"})
    found = check.problems()
    assert any("has no nowhere.txt" in problem for problem in found)
    assert any("because it is needed" in problem for problem in found)


def test_a_package_the_wheel_cannot_find_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "declared_packages", lambda: ["src/nowhere"])
    assert any("which is not there" in problem for problem in check.problems())


def test_a_wheel_told_to_include_nothing_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "declared_packages", list)
    assert any("not told which packages" in problem for problem in check.problems())


def test_a_missing_console_script_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "scripts", dict)
    assert any("declares no 'shearstud' console script" in p for p in check.problems())


def test_a_console_script_pointing_somewhere_else_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(check, "scripts", lambda: {check.SCRIPT_NAME: "shearstud:nowhere"})
    assert any("points at 'shearstud:nowhere'" in problem for problem in check.problems())


def test_the_metadata_reads() -> None:
    loaded = check.config()
    assert loaded["project"]["name"] == "shearstud"  # type: ignore[index]


def test_the_contents_list_what_would_ship() -> None:
    listed = check.contents()
    assert any("subpackages" in line for line in listed)
    assert any("py.typed" in line for line in listed)
    assert any("script shearstud" in line for line in listed)


def test_the_contents_print_on_request(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main(["--list"]) == 0
    assert "check_package: py.typed: present" in capsys.readouterr().out


def test_a_problem_is_reported_and_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(check, "problems", lambda: ["the wheel would be missing something"])
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert "check_package: the wheel would be missing something" in out
    assert "1 problem(s)" in out
