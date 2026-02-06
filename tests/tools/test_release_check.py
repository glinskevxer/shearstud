"""The release gate, and the discovery that stops a check going unrun."""

from __future__ import annotations

import pytest

from shearstud.tools import release_check as release

pytestmark = pytest.mark.tools


def test_every_check_module_is_discovered() -> None:
    names = release.check_modules()
    for expected in ("check_docstrings", "check_layers", "check_sql", "check_units"):
        assert expected in names


def test_every_builder_is_discovered() -> None:
    names = release.builder_modules()
    for expected in ("build_architecture", "build_commands", "build_glossary", "schema_dump"):
        assert expected in names


def test_the_lock_builder_runs_with_the_documents() -> None:
    assert "build_lock" in release.builder_modules()


def test_the_names_come_back_sorted() -> None:
    assert release.check_modules() == sorted(release.check_modules())
    assert release.builder_modules() == sorted(release.builder_modules())


def test_discovery_finds_every_check_on_disk() -> None:
    from shearstud.tools.walk import PACKAGE_ROOT

    on_disk = sorted(path.stem for path in (PACKAGE_ROOT / "tools").glob("check_*.py"))
    assert release.check_modules() == on_disk


def test_no_check_module_is_also_a_builder() -> None:
    assert set(release.check_modules()) & set(release.builder_modules()) == set()


def test_every_discovered_module_has_a_main() -> None:
    import importlib

    for name in release.check_modules() + release.builder_modules():
        module = importlib.import_module(f"shearstud.tools.{name}")
        assert callable(module.main), name


def test_every_gate_comes_back_clean() -> None:
    failed = [result.name for result in release.gates() if not result.passed]
    assert failed == []


def test_the_gate_count_matches_what_ran() -> None:
    results = release.gates()
    assert len(results) == release.counts()["gates"]


def test_the_smoke_run_is_one_of_the_gates() -> None:
    assert "smoke" in {result.name for result in release.gates()}


def test_a_passing_gate_says_so() -> None:
    assert release.GateResult("check_x", 0).passed
    assert not release.GateResult("check_x", 1).passed


def test_the_counts_are_plausible() -> None:
    numbers = release.counts()
    assert numbers["modules"] > 50
    assert numbers["source_lines"] > 5000
    assert numbers["test_files"] > 40
    assert numbers["test_lines"] > 5000


def test_the_command_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert release.main(["--quiet"]) == 0
    assert "gates clean" in capsys.readouterr().out


def test_the_command_prints_the_counts(capsys: pytest.CaptureFixture[str]) -> None:
    release.main([])
    out = capsys.readouterr().out
    assert "modules" in out
    assert "source lines" in out


def test_a_failing_gate_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        release,
        "gates",
        lambda: [release.GateResult("check_x", 1), release.GateResult("check_y", 0)],
    )
    assert release.main(["--quiet"]) == 1
    out = capsys.readouterr().out
    assert "FAILED check_x" in out
    assert "1 of 2 gates failed" in out
