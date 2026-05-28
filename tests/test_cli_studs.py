"""The stud command, which reports two checks and does not average them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from shearstud.cli import main
from tests.support import NUMBER, document

pytestmark = pytest.mark.cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def loaded(runner: CliRunner, book: Path, tmp_path: Path) -> Path:
    doc = tmp_path / "structure.json"
    doc.write_text(json.dumps(document()), encoding="utf-8")
    result = runner.invoke(
        main,
        ["--book", str(book), "structure", "import", str(doc), "--adtt", "1200", "--grade", "A36"],
    )
    assert result.exit_code == 0, result.output
    return book


def call(runner: CliRunner, book: Path, *extra: str) -> Result:
    argv = ["--book", str(book), "studs", NUMBER, "G2", "--stations", "4", *extra]
    return runner.invoke(main, argv)


def test_the_command_reports_both_checks(runner: CliRunner, loaded: Path) -> None:
    # Fatigue answers in inches and strength answers in rows. Reporting one of
    # them as "the stud design" is how a girder gets the right total number of
    # studs at the wrong spacing.
    result = call(runner, loaded)
    assert result.exit_code == 0, result.output
    assert "fatigue" in result.output
    assert "strength" in result.output


def test_the_fatigue_check_answers_in_inches(runner: CliRunner, loaded: Path) -> None:
    assert "in pitch" in call(runner, loaded).output


def test_the_strength_check_answers_in_rows(runner: CliRunner, loaded: Path) -> None:
    assert "row(s) between maximum moment and zero moment" in call(runner, loaded).output


def test_the_pitch_limits_are_printed(runner: CliRunner, loaded: Path) -> None:
    result = call(runner, loaded)
    assert "limits   pitch between" in result.output


def test_the_pitch_lands_inside_its_limits(runner: CliRunner, loaded: Path) -> None:
    result = call(runner, loaded)
    low, high = _limits(result)
    assert low <= _pitch(result) <= high


def test_a_bigger_stud_has_wider_limits(runner: CliRunner, loaded: Path) -> None:
    small = _limits(call(runner, loaded, "--diameter-in", "0.625"))
    large = _limits(call(runner, loaded, "--diameter-in", "1.0"))
    assert large[0] > small[0]


def test_more_studs_per_row_allows_a_wider_pitch(runner: CliRunner, loaded: Path) -> None:
    two = _pitch(call(runner, loaded, "--per-row", "2"))
    four = _pitch(call(runner, loaded, "--per-row", "4"))
    assert four > two


def test_more_studs_per_row_needs_fewer_rows(runner: CliRunner, loaded: Path) -> None:
    two = _rows(call(runner, loaded, "--per-row", "2"))
    four = _rows(call(runner, loaded, "--per-row", "4"))
    assert four < two


def test_a_finite_design_life_is_harder_than_an_infinite_one(
    runner: CliRunner, loaded: Path
) -> None:
    infinite = _pitch(call(runner, loaded))
    finite = _pitch(call(runner, loaded, "--cycles", "1e8"))
    assert finite <= infinite


def test_a_non_standard_diameter_is_called_out(runner: CliRunner, loaded: Path) -> None:
    result = call(runner, loaded, "--diameter-in", "0.8")
    assert "is not a standard diameter" in result.output


def test_a_standard_diameter_is_not_called_out(runner: CliRunner, loaded: Path) -> None:
    assert "not a standard diameter" not in call(runner, loaded, "--diameter-in", "0.75").output


def test_a_stud_too_short_for_its_diameter_is_refused(runner: CliRunner, loaded: Path) -> None:
    result = call(runner, loaded, "--diameter-in", "1.0", "--height-in", "2.0")
    assert result.exit_code != 0
    assert "needs to be at least" in result.output


def test_the_command_says_what_governs_one_stud(runner: CliRunner, loaded: Path) -> None:
    result = call(runner, loaded)
    assert "governs" in result.output
    assert "kip" in result.output


def test_the_command_names_the_station_the_pitch_came_from(runner: CliRunner, loaded: Path) -> None:
    assert "governed at" in call(runner, loaded).output


def test_a_girder_that_is_not_there_is_refused(runner: CliRunner, loaded: Path) -> None:
    result = runner.invoke(main, ["--book", str(loaded), "studs", NUMBER, "G9"])
    assert result.exit_code != 0


def test_a_structure_that_is_not_there_is_refused(runner: CliRunner, loaded: Path) -> None:
    result = runner.invoke(main, ["--book", str(loaded), "studs", "99-XX-9999", "G2"])
    assert result.exit_code != 0


def test_the_command_appears_in_the_help(runner: CliRunner) -> None:
    assert "studs" in runner.invoke(main, ["--help"]).output


def _pitch(result: Result) -> float:
    line = next(line for line in result.output.splitlines() if line.startswith("fatigue "))
    return float(line.split()[1])


def _rows(result: Result) -> int:
    line = next(line for line in result.output.splitlines() if "row(s) between" in line)
    return int(line.split()[1])


def _limits(result: Result) -> tuple[float, float]:
    line = next(line for line in result.output.splitlines() if line.startswith("limits"))
    parts = line.split("between")[1].split("and")
    return float(parts[0]), float(parts[1].replace("in", "").strip())
