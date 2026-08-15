"""The shape commands, and the idealisation gap they exist to make visible."""

from __future__ import annotations

import pytest
from click.testing import CliRunner, Result

from shearstud.cli import main
from shearstud.geometry import rolled

pytestmark = pytest.mark.cli


def call(runner: CliRunner, *words: str) -> Result:
    return runner.invoke(main, ["shape", *words])


def test_the_listing_names_every_shape(runner: CliRunner) -> None:
    result = call(runner, "list")
    assert result.exit_code == 0, result.output
    assert f"{len(rolled.designations())} shape(s)" in result.output


def test_the_listing_can_be_narrowed_by_prefix(runner: CliRunner) -> None:
    result = call(runner, "list", "--starts-with", "W30")
    assert "W30X116" in result.output
    assert "W14X48" not in result.output


def test_the_prefix_is_not_case_sensitive(runner: CliRunner) -> None:
    assert "W30X116" in call(runner, "list", "--starts-with", "w30").output


def test_a_prefix_nothing_matches_lists_nothing(runner: CliRunner) -> None:
    result = call(runner, "list", "--starts-with", "HP99")
    assert "0 shape(s)" in result.output


def test_the_listing_can_be_sorted_by_depth(runner: CliRunner) -> None:
    result = call(runner, "list", "--sort-depth")
    depths = [
        float(line.split("deep")[0].split()[-1])
        for line in result.output.splitlines()
        if "deep" in line
    ]
    assert depths == sorted(depths, reverse=True)


def test_a_shape_reports_its_published_dimensions(runner: CliRunner) -> None:
    result = call(runner, "show", "W30X116")
    assert result.exit_code == 0, result.output
    assert "published" in result.output
    assert "4930" in result.output


def test_a_shape_reports_what_the_idealisation_makes_of_it(runner: CliRunner) -> None:
    result = call(runner, "show", "W30X116")
    assert "idealised" in result.output
    assert "which is the fillets" in result.output


def test_the_idealised_inertia_is_below_the_published_one(runner: CliRunner) -> None:
    # Three rectangles throw the fillets away, so the idealisation is always
    # a little light. It being heavier would mean the arithmetic is wrong.
    result = call(runner, "show", "W30X116")
    published = _number(result, "published", "I")
    idealised = _number(result, "idealised", "I")
    assert idealised < published


def test_the_clear_web_depth_is_less_than_the_overall_depth(runner: CliRunner) -> None:
    result = call(runner, "show", "W30X116")
    line = next(line for line in result.output.splitlines() if line.startswith("depth"))
    overall = float(line.split()[1])
    clear = float(line.split("web")[1].split()[0])
    assert clear < overall


def test_a_shape_nobody_rolls_is_refused(runner: CliRunner) -> None:
    result = call(runner, "show", "W99X999")
    assert result.exit_code != 0


def test_the_comparison_puts_the_worst_fit_first(runner: CliRunner) -> None:
    result = call(runner, "compare")
    assert result.exit_code == 0, result.output
    errors = [
        float(line.split("%")[0].split()[-1])
        for line in result.output.splitlines()
        if "published" in line
    ]
    assert errors == sorted(errors, reverse=True)


def test_the_comparison_can_be_cut_to_a_length(runner: CliRunner) -> None:
    listed = [line for line in call(runner, "compare", "--worst", "2").output.splitlines()]
    assert len([line for line in listed if "published" in line]) == 2


def test_the_worst_fit_is_a_deep_narrow_flanged_shape(runner: CliRunner) -> None:
    # The fillet is a larger share of a section that has less flange in it.
    result = call(runner, "compare", "--worst", "1")
    worst = next(line for line in result.output.splitlines() if "published" in line)
    found = rolled.shape(worst.split()[0])
    assert found.depth_in / found.flange_width_in > 2.0


def test_the_worst_fit_is_inside_the_tolerance_the_package_allows(
    runner: CliRunner,
) -> None:
    result = call(runner, "compare", "--worst", "1")
    line = next(line for line in result.output.splitlines() if line.startswith("worst fit"))
    assert float(line.split("%")[0].split()[-1]) / 100.0 <= rolled.IDEALISATION_TOLERANCE_FRAC


def test_a_comparison_of_nothing_is_refused(runner: CliRunner) -> None:
    assert call(runner, "compare", "--worst", "0").exit_code != 0


def test_the_group_appears_in_the_help(runner: CliRunner) -> None:
    assert "shape" in runner.invoke(main, ["--help"]).output


def _number(result: Result, label: str, symbol: str) -> float:
    line = next(line for line in result.output.splitlines() if line.startswith(label))
    return float(line.split(symbol)[1].split()[0])
