"""The vehicle and permit commands.

The permit tests are the ones that matter. Printing every control and not only
the one that was asked for is the whole design: an engineer deciding whether to
escort a load needs to see that escorting would have made it issuable.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from shearstud.cli import main
from shearstud.loads import vehicles
from tests.support import NUMBER

pytestmark = pytest.mark.cli


def call(runner: CliRunner, *words: str) -> Result:
    return runner.invoke(main, ["vehicle", *words])


def test_the_listing_names_every_vehicle(runner: CliRunner) -> None:
    result = call(runner, "list")
    assert result.exit_code == 0, result.output
    for name in vehicles.names():
        assert name in result.output
    assert f"{len(vehicles.names())} vehicle(s)" in result.output


def test_the_listing_can_be_cut_to_one_class(runner: CliRunner) -> None:
    result = call(runner, "list", "--class", "legal")
    assert "TYPE3" in result.output
    assert "HL93-TRUCK" not in result.output


def test_a_class_nobody_rates_is_refused(runner: CliRunner) -> None:
    assert call(runner, "list", "--class", "oversize").exit_code != 0


def test_the_listing_can_be_sorted_by_weight(runner: CliRunner) -> None:
    result = call(runner, "list", "--sort-weight")
    weights = [
        float(line.split("kip")[0].split()[-1])
        for line in result.output.splitlines()
        if "kip" in line
    ]
    assert weights == sorted(weights, reverse=True)


def test_a_vehicle_reports_its_axles(runner: CliRunner) -> None:
    result = call(runner, "show", "TYPE3")
    assert result.exit_code == 0, result.output
    assert "gross    50.0 kip" in result.output
    assert result.output.count("kip cumulative") == 3


def test_the_cumulative_weight_reaches_the_gross(runner: CliRunner) -> None:
    result = call(runner, "show", "TYPE3")
    last = [line for line in result.output.splitlines() if "cumulative" in line][-1]
    assert "50.0 kip cumulative" in last


def test_the_distance_from_the_lead_axle_is_accumulated(runner: CliRunner) -> None:
    # The axles carry the gap to the one in front, so printing the spacing
    # alone would say a 19 foot truck is 4 feet long.
    result = call(runner, "show", "TYPE3")
    assert "0.0 ft from lead" in result.output
    assert "19.0 ft from lead" in result.output


def test_a_vehicle_nobody_has_is_refused(runner: CliRunner) -> None:
    result = call(runner, "show", "ROADTRAIN")
    assert result.exit_code != 0


def test_the_envelope_is_largest_at_midspan(runner: CliRunner) -> None:
    result = call(runner, "envelope", "TYPE3", "--span-ft", "90", "--points", "4")
    assert result.exit_code == 0, result.output
    moments = [
        float(line.split("kipft")[0].split()[-1])
        for line in result.output.splitlines()
        if "kipft" in line
    ]
    assert max(moments) == moments[len(moments) // 2]


def test_the_envelope_is_symmetric_about_midspan(runner: CliRunner) -> None:
    result = call(runner, "envelope", "TYPE3", "--span-ft", "90", "--points", "4")
    moments = [
        float(line.split("kipft")[0].split()[-1])
        for line in result.output.splitlines()
        if "kipft" in line
    ]
    assert moments[0] == pytest.approx(moments[-1])


def test_a_heavier_vehicle_puts_more_moment_on(runner: CliRunner) -> None:
    def midspan(name: str) -> float:
        result = call(runner, "envelope", name, "--span-ft", "90", "--points", "2")
        line = next(line for line in result.output.splitlines() if "kipft" in line)
        return float(line.split("kipft")[0].split()[-1])

    assert midspan("TYPE3-3") > midspan("TYPE3")


def test_an_envelope_of_one_point_is_refused(runner: CliRunner) -> None:
    assert call(runner, "envelope", "TYPE3", "--span-ft", "90", "--points", "1").exit_code != 0


def test_a_permit_prints_a_line_per_control(runner: CliRunner, imported_book: Path) -> None:
    result = runner.invoke(
        main, ["--book", str(imported_book), "permit", NUMBER, "TYPE3", "--stations", "4"]
    )
    assert result.exit_code == 0, result.output
    assert "mixed" in result.output
    assert "escorted" in result.output


def test_escorting_gives_a_better_rating_than_mixing(
    runner: CliRunner, imported_book: Path
) -> None:
    # The whole reason both are printed. An agency that always answers
    # "escorted" is charging for margin it does not need, and one that never
    # offers it refuses loads that could cross.
    result = runner.invoke(
        main, ["--book", str(imported_book), "permit", NUMBER, "TYPE3", "--stations", "4"]
    )
    assert _rating(result, "mixed") < _rating(result, "escorted")


def test_a_routine_permit_has_no_escorted_line(runner: CliRunner, imported_book: Path) -> None:
    # Nobody escorts a vehicle that crosses unannounced.
    result = runner.invoke(
        main,
        [
            "--book",
            str(imported_book),
            "permit",
            NUMBER,
            "TYPE3",
            "--stations",
            "4",
            "--kind",
            "routine",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "escorted" not in result.output


def test_a_permit_that_clears_says_how_to_issue_it(runner: CliRunner, imported_book: Path) -> None:
    result = runner.invoke(
        main, ["--book", str(imported_book), "permit", NUMBER, "TYPE3", "--stations", "4"]
    )
    assert "issue as single_trip" in result.output
    assert "margin over the load" in result.output


def test_the_loosest_control_that_clears_is_the_one_offered(
    runner: CliRunner, imported_book: Path
) -> None:
    result = runner.invoke(
        main, ["--book", str(imported_book), "permit", NUMBER, "TYPE3", "--stations", "4"]
    )
    if _rating(result, "mixed") >= 1.0:
        assert "single_trip mixed" in result.output


def test_a_permit_nothing_clears_says_so_rather_than_failing(
    runner: CliRunner, imported_book: Path
) -> None:
    # A permit that cannot be issued is an answer, and it is the one the
    # haulier is waiting for.
    result = runner.invoke(
        main,
        [
            "--book",
            str(imported_book),
            "permit",
            NUMBER,
            "TYPE3",
            "--stations",
            "4",
            "--overlay",
            "60",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "cannot cross" in result.output


def test_a_permit_kind_nobody_issues_is_refused(runner: CliRunner, imported_book: Path) -> None:
    result = runner.invoke(
        main,
        ["--book", str(imported_book), "permit", NUMBER, "TYPE3", "--kind", "provisional"],
    )
    assert result.exit_code != 0


def test_a_permit_on_a_structure_that_is_not_there_is_refused(
    runner: CliRunner, imported_book: Path
) -> None:
    result = runner.invoke(main, ["--book", str(imported_book), "permit", "99-XX-9999", "TYPE3"])
    assert result.exit_code != 0


def test_the_group_appears_in_the_help(runner: CliRunner) -> None:
    output = runner.invoke(main, ["--help"]).output
    assert "vehicle" in output
    assert "permit" in output


def _rating(result: Result, control: str) -> float:
    line = next(line for line in result.output.splitlines() if line.startswith(control))
    return float(line.split("RF")[1].split()[0])
