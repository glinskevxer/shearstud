"""The release gate, and the discovery that stops a check going unrun.

Every gate is run once for the whole module and every question is asked of that
one result. Running them takes about twenty seconds, because it is every self
check in the package plus the end to end smoke run, and five tests each doing
it for themselves was two minutes of a two and a half minute suite.
"""

from __future__ import annotations

import pytest

from shearstud.tools import release_check as release

pytestmark = pytest.mark.tools


@pytest.fixture(scope="module")
def gate_results() -> list[release.GateResult]:
    """Every gate, run once."""
    return release.gates()


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


def test_every_gate_comes_back_clean(gate_results: list[release.GateResult]) -> None:
    failed = [result.name for result in gate_results if not result.passed]
    assert failed == []


def test_the_gate_count_matches_what_ran(gate_results: list[release.GateResult]) -> None:
    assert len(gate_results) == release.counts()["gates"]


def test_the_smoke_run_is_one_of_the_gates(gate_results: list[release.GateResult]) -> None:
    assert "smoke" in {result.name for result in gate_results}


def test_every_check_module_is_one_of_the_gates(
    gate_results: list[release.GateResult],
) -> None:
    ran = {result.name for result in gate_results}
    assert set(release.check_modules()) <= ran
    assert set(release.builder_modules()) <= ran


def test_a_passing_gate_says_so() -> None:
    assert release.GateResult("check_x", 0).passed
    assert not release.GateResult("check_x", 1).passed


def test_the_counts_are_plausible() -> None:
    numbers = release.counts()
    assert numbers["modules"] > 50
    assert numbers["source_lines"] > 5000
    assert numbers["test_files"] > 40
    assert numbers["test_lines"] > 5000


def test_the_command_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    gate_results: list[release.GateResult],
) -> None:
    # Against the gates the module already ran. Running them again here says
    # nothing the clean gate test has not, and costs twenty seconds to say it.
    monkeypatch.setattr(release, "gates", lambda: gate_results)
    assert release.main(["--quiet"]) == 0
    assert "gates clean" in capsys.readouterr().out


def test_the_command_prints_the_counts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    gate_results: list[release.GateResult],
) -> None:
    monkeypatch.setattr(release, "gates", lambda: gate_results)
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


def test_nothing_has_fallen_below_its_floor() -> None:
    assert release.shortfalls() == []


def test_every_floor_is_a_count_the_command_reports() -> None:
    numbers = release.counts()
    assert set(release.FLOORS) <= set(numbers)


def test_every_floor_is_comfortably_below_where_the_repository_stands() -> None:
    # A floor set just under today's number is a floor somebody raises every
    # week until they stop reading it.
    numbers = release.counts()
    for name, floor in release.FLOORS.items():
        assert numbers[name] > floor, name


def test_a_count_below_its_floor_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release, "counts", lambda: dict.fromkeys(release.FLOORS, 0))
    found = release.shortfalls()
    assert len(found) == len(release.FLOORS)
    assert all("below the floor of" in line for line in found)


def test_a_count_that_is_missing_altogether_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(release, "counts", lambda: {})
    assert len(release.shortfalls()) == len(release.FLOORS)


def test_a_shrunken_repository_fails_even_with_every_gate_clean(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    gate_results: list[release.GateResult],
) -> None:
    # A repository that has lost half its tests passes every gate it still
    # has, which is why this is checked apart from them.
    monkeypatch.setattr(release, "gates", lambda: gate_results)
    monkeypatch.setattr(release, "counts", lambda: dict.fromkeys(release.FLOORS, 0))
    assert release.main(["--quiet"]) == 1
    out = capsys.readouterr().out
    assert "SHRANK" in out
    assert "below the floor" in out


def test_a_failing_gate_is_reported_before_a_shortfall(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(release, "gates", lambda: [release.GateResult("check_x", 1)])
    monkeypatch.setattr(release, "counts", lambda: dict.fromkeys(release.FLOORS, 0))
    assert release.main(["--quiet"]) == 1
    out = capsys.readouterr().out
    assert out.index("FAILED") < out.index("SHRANK")
