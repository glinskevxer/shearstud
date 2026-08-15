"""The thickness commands, and rating with the loss the meter found."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from shearstud.cli import main
from shearstud.store import db

pytestmark = pytest.mark.cli

NUMBER = "18-SH-0473"


def call(runner: CliRunner, path: Path, *words: str) -> Result:
    return runner.invoke(main, ["--book", str(path), "thickness", *words])


def add(
    runner: CliRunner,
    path: Path,
    station_ft: float = 10.0,
    remaining_in: float = 1.20,
    when: str = "2026-04-02",
    girder_id: str = "G1",
    plate: str = "bottom",
    note: str = "",
) -> Result:
    argv = [
        "add",
        NUMBER,
        girder_id,
        plate,
        "--station-ft",
        str(station_ft),
        "--remaining-in",
        str(remaining_in),
        "--measured",
        when,
    ]
    if note:
        argv.extend(["--note", note])
    return call(runner, path, *argv)


def sheet(tmp_path: Path) -> Path:
    path = tmp_path / "sheet.csv"
    path.write_text(
        "plate,station_ft,remaining_in,note\n"
        "bottom,10.0,1.20,under the joint\n"
        "bottom,60.0,1.42,\n"
        "web,10.0,0.48,pitting\n",
        encoding="utf-8",
    )
    return path


def test_a_reading_is_recorded(runner: CliRunner, imported_book: Path) -> None:
    result = add(runner, imported_book)
    assert result.exit_code == 0, result.output
    assert "recorded bottom at 10 ft on G1" in result.output
    assert db.row_count(imported_book, "thickness_readings") == 1


def test_a_reading_keeps_its_note(runner: CliRunner, imported_book: Path) -> None:
    add(runner, imported_book, note="under the leaking joint")
    assert "under the leaking joint" in call(runner, imported_book, "list", NUMBER).output


def test_a_reading_on_a_girder_that_is_not_there_is_refused(
    runner: CliRunner, imported_book: Path
) -> None:
    assert add(runner, imported_book, girder_id="G9").exit_code != 0


def test_a_date_that_is_not_a_date_is_refused(runner: CliRunner, imported_book: Path) -> None:
    assert add(runner, imported_book, when="last tuesday").exit_code != 0


def test_a_whole_sheet_can_be_imported(
    runner: CliRunner, imported_book: Path, tmp_path: Path
) -> None:
    result = call(
        runner,
        imported_book,
        "import",
        NUMBER,
        "G1",
        str(sheet(tmp_path)),
        "--measured",
        "2026-04-02",
    )
    assert result.exit_code == 0, result.output
    assert "recorded 3 reading(s)" in result.output
    assert db.row_count(imported_book, "thickness_readings") == 3


def test_an_imported_sheet_keeps_its_notes(
    runner: CliRunner, imported_book: Path, tmp_path: Path
) -> None:
    call(
        runner,
        imported_book,
        "import",
        NUMBER,
        "G1",
        str(sheet(tmp_path)),
        "--measured",
        "2026-04-02",
    )
    assert "under the joint" in call(runner, imported_book, "list", NUMBER).output


def test_a_sheet_row_with_too_few_columns_is_refused(
    runner: CliRunner, imported_book: Path, tmp_path: Path
) -> None:
    path = tmp_path / "short.csv"
    path.write_text("plate,station_ft,remaining_in\nbottom,10.0\n", encoding="utf-8")
    result = call(
        runner, imported_book, "import", NUMBER, "G1", str(path), "--measured", "2026-04-02"
    )
    assert result.exit_code != 0
    assert "needs a plate, a station and a thickness" in result.output


def test_a_sheet_row_that_is_not_numbers_is_refused(
    runner: CliRunner, imported_book: Path, tmp_path: Path
) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("plate,station_ft,remaining_in\nbottom,10.0,1.2\nweb,x,y\n", encoding="utf-8")
    result = call(
        runner, imported_book, "import", NUMBER, "G1", str(path), "--measured", "2026-04-02"
    )
    assert result.exit_code != 0
    assert "are not numbers" in result.output


def test_an_empty_sheet_is_refused(runner: CliRunner, imported_book: Path, tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("plate,station_ft,remaining_in\n", encoding="utf-8")
    result = call(
        runner, imported_book, "import", NUMBER, "G1", str(path), "--measured", "2026-04-02"
    )
    assert result.exit_code != 0
    assert "holds no readings" in result.output


def test_a_structure_with_no_readings_says_so(runner: CliRunner, imported_book: Path) -> None:
    assert "no readings" in call(runner, imported_book, "list", NUMBER).output


def test_the_listing_counts_the_locations(runner: CliRunner, imported_book: Path) -> None:
    add(runner, imported_book, station_ft=10.0)
    add(runner, imported_book, station_ft=60.0)
    assert "2 reading(s) on 2 location(s)" in call(runner, imported_book, "list", NUMBER).output


def test_the_listing_can_be_narrowed_to_a_girder(runner: CliRunner, imported_book: Path) -> None:
    add(runner, imported_book, girder_id="G1")
    add(runner, imported_book, girder_id="G2")
    result = call(runner, imported_book, "list", NUMBER, "--girder", "G1")
    assert "G2" not in result.output
    assert "1 reading(s)" in result.output


def test_the_newest_flag_collapses_a_place_to_one_reading(
    runner: CliRunner, imported_book: Path
) -> None:
    add(runner, imported_book, remaining_in=1.46, when="2019-04-02")
    add(runner, imported_book, remaining_in=1.35, when="2026-04-02")
    everything = call(runner, imported_book, "list", NUMBER)
    newest = call(runner, imported_book, "list", NUMBER, "--newest")
    assert "2 reading(s)" in everything.output
    assert "1 reading(s)" in newest.output
    assert "1.460" not in newest.output


def test_the_loss_report_names_the_nominal_and_what_went(
    runner: CliRunner, imported_book: Path
) -> None:
    add(runner, imported_book, remaining_in=1.20)
    result = call(runner, imported_book, "loss", NUMBER, "G1")
    assert result.exit_code == 0, result.output
    assert "1.500 nominal" in result.output
    assert "0.300 lost" in result.output


def test_a_loss_over_a_tenth_is_a_finding(runner: CliRunner, imported_book: Path) -> None:
    add(runner, imported_book, remaining_in=1.30)
    assert "finding" in call(runner, imported_book, "loss", NUMBER, "G1").output


def test_a_loss_over_a_quarter_is_severe(runner: CliRunner, imported_book: Path) -> None:
    add(runner, imported_book, remaining_in=1.00)
    assert "severe" in call(runner, imported_book, "loss", NUMBER, "G1").output


def test_a_small_loss_is_only_a_note(runner: CliRunner, imported_book: Path) -> None:
    add(runner, imported_book, remaining_in=1.45)
    result = call(runner, imported_book, "loss", NUMBER, "G1")
    assert "note" in result.output
    assert "severe" not in result.output


def test_the_loss_report_says_what_is_left_of_the_section(
    runner: CliRunner, imported_book: Path
) -> None:
    add(runner, imported_book, remaining_in=1.20)
    assert "of nominal" in call(runner, imported_book, "loss", NUMBER, "G1").output


def test_a_girder_with_no_readings_has_no_loss_report(
    runner: CliRunner, imported_book: Path
) -> None:
    add(runner, imported_book, girder_id="G1")
    assert "no readings on G2" in call(runner, imported_book, "loss", NUMBER, "G2").output


def test_a_place_measured_once_gives_no_rate(runner: CliRunner, imported_book: Path) -> None:
    add(runner, imported_book)
    result = call(runner, imported_book, "rate", NUMBER)
    assert "none measured more than once" in result.output


def test_a_place_measured_twice_gives_a_rate(runner: CliRunner, imported_book: Path) -> None:
    add(runner, imported_book, remaining_in=1.46, when="2019-04-02")
    add(runner, imported_book, remaining_in=1.32, when="2026-04-02")
    result = call(runner, imported_book, "rate", NUMBER)
    assert "in/yr" in result.output
    assert "2 reading(s)" in result.output


def test_a_structure_with_no_readings_has_no_rates(runner: CliRunner, imported_book: Path) -> None:
    assert "no readings" in call(runner, imported_book, "rate", NUMBER).output


def test_rating_the_measured_sections_says_it_is_doing_so(
    runner: CliRunner, imported_book: Path
) -> None:
    add(runner, imported_book, remaining_in=1.10)
    result = runner.invoke(
        main, ["--book", str(imported_book), "rate", NUMBER, "--stations", "4", "--measured"]
    )
    assert result.exit_code == 0, result.output
    assert "with section loss from its readings" in result.output


def test_asking_for_measured_sections_with_none_says_so(
    runner: CliRunner, imported_book: Path
) -> None:
    # Not an error, and not silently the same thing either.
    result = runner.invoke(
        main, ["--book", str(imported_book), "rate", NUMBER, "--stations", "4", "--measured"]
    )
    assert result.exit_code == 0
    assert "no thickness readings, rating the drawing sections" in result.output


def test_section_loss_lowers_the_rating(runner: CliRunner, imported_book: Path) -> None:
    nominal = runner.invoke(main, ["--book", str(imported_book), "rate", NUMBER, "--stations", "4"])
    add(runner, imported_book, remaining_in=1.00, girder_id="G1")
    add(runner, imported_book, remaining_in=1.00, girder_id="G2")
    add(runner, imported_book, remaining_in=1.00, girder_id="G3")
    add(runner, imported_book, remaining_in=1.00, girder_id="G4")
    measured = runner.invoke(
        main, ["--book", str(imported_book), "rate", NUMBER, "--stations", "4", "--measured"]
    )
    assert _governing(measured) < _governing(nominal)


def test_section_loss_lowers_the_shear_rating(runner: CliRunner, imported_book: Path) -> None:
    nominal = runner.invoke(
        main, ["--book", str(imported_book), "shear", NUMBER, "--stations", "4"]
    )
    for girder_id in ("G1", "G2", "G3", "G4"):
        add(
            runner,
            imported_book,
            plate="web",
            remaining_in=0.375,
            girder_id=girder_id,
            station_ft=1.0,
        )
    measured = runner.invoke(
        main, ["--book", str(imported_book), "shear", NUMBER, "--stations", "4", "--measured"]
    )
    assert _shear(measured) < _shear(nominal)


def test_the_group_appears_in_the_help(runner: CliRunner) -> None:
    assert "thickness" in runner.invoke(main, ["--help"]).output


def _governing(result: Result) -> float:
    line = next(line for line in result.output.splitlines() if "governing RF" in line)
    return float(line.split("governing RF")[1].split()[0])


def _shear(result: Result) -> float:
    line = next(line for line in result.output.splitlines() if "governing shear RF" in line)
    return float(line.split("governing shear RF")[1].split()[0])
