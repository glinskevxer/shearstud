"""The thickness commands, and rating with the loss the meter found."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from shearstud.cli import main
from shearstud.store import db

pytestmark = pytest.mark.cli

NUMBER = "18-SH-0473"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def document(bottom_in: float = 1.5) -> dict[str, Any]:
    plates = [
        {"label": "bottom", "width_in": 18.0, "height_in": bottom_in, "y_center_in": 0.75},
        {"label": "web", "width_in": 0.5625, "height_in": 52.0, "y_center_in": 27.5},
        {"label": "top", "width_in": 16.0, "height_in": 1.0, "y_center_in": 54.0},
    ]
    girders = []
    for index in range(4):
        exterior = index in (0, 3)
        girders.append(
            {
                "girder_id": f"G{index + 1}",
                "girder_index": index,
                "spacing_left_ft": 0.0 if index == 0 else 8.0,
                "spacing_right_ft": 0.0 if index == 3 else 8.0,
                "overhang_ft": 3.5 if exterior else 0.0,
                "slab_thickness_in": 8.0,
                "haunch_in": 2.0,
                "deck_fc_ksi": 4.0,
                "runs": [{"from_station_ft": 0.0, "to_station_ft": 90.0, "plates": plates}],
                "details": [],
            }
        )
    return {
        "number": NUMBER,
        "name": "Salt Fork Creek",
        "year_built": 1968,
        "spans": [90.0],
        "girders": girders,
    }


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


def test_a_reading_is_recorded(runner: CliRunner, loaded: Path) -> None:
    result = add(runner, loaded)
    assert result.exit_code == 0, result.output
    assert "recorded bottom at 10 ft on G1" in result.output
    assert db.row_count(loaded, "thickness_readings") == 1


def test_a_reading_keeps_its_note(runner: CliRunner, loaded: Path) -> None:
    add(runner, loaded, note="under the leaking joint")
    assert "under the leaking joint" in call(runner, loaded, "list", NUMBER).output


def test_a_reading_on_a_girder_that_is_not_there_is_refused(
    runner: CliRunner, loaded: Path
) -> None:
    assert add(runner, loaded, girder_id="G9").exit_code != 0


def test_a_date_that_is_not_a_date_is_refused(runner: CliRunner, loaded: Path) -> None:
    assert add(runner, loaded, when="last tuesday").exit_code != 0


def test_a_whole_sheet_can_be_imported(runner: CliRunner, loaded: Path, tmp_path: Path) -> None:
    result = call(
        runner, loaded, "import", NUMBER, "G1", str(sheet(tmp_path)), "--measured", "2026-04-02"
    )
    assert result.exit_code == 0, result.output
    assert "recorded 3 reading(s)" in result.output
    assert db.row_count(loaded, "thickness_readings") == 3


def test_an_imported_sheet_keeps_its_notes(runner: CliRunner, loaded: Path, tmp_path: Path) -> None:
    call(runner, loaded, "import", NUMBER, "G1", str(sheet(tmp_path)), "--measured", "2026-04-02")
    assert "under the joint" in call(runner, loaded, "list", NUMBER).output


def test_a_sheet_row_with_too_few_columns_is_refused(
    runner: CliRunner, loaded: Path, tmp_path: Path
) -> None:
    path = tmp_path / "short.csv"
    path.write_text("plate,station_ft,remaining_in\nbottom,10.0\n", encoding="utf-8")
    result = call(runner, loaded, "import", NUMBER, "G1", str(path), "--measured", "2026-04-02")
    assert result.exit_code != 0
    assert "needs a plate, a station and a thickness" in result.output


def test_a_sheet_row_that_is_not_numbers_is_refused(
    runner: CliRunner, loaded: Path, tmp_path: Path
) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("plate,station_ft,remaining_in\nbottom,10.0,1.2\nweb,x,y\n", encoding="utf-8")
    result = call(runner, loaded, "import", NUMBER, "G1", str(path), "--measured", "2026-04-02")
    assert result.exit_code != 0
    assert "are not numbers" in result.output


def test_an_empty_sheet_is_refused(runner: CliRunner, loaded: Path, tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("plate,station_ft,remaining_in\n", encoding="utf-8")
    result = call(runner, loaded, "import", NUMBER, "G1", str(path), "--measured", "2026-04-02")
    assert result.exit_code != 0
    assert "holds no readings" in result.output


def test_a_structure_with_no_readings_says_so(runner: CliRunner, loaded: Path) -> None:
    assert "no readings" in call(runner, loaded, "list", NUMBER).output


def test_the_listing_counts_the_locations(runner: CliRunner, loaded: Path) -> None:
    add(runner, loaded, station_ft=10.0)
    add(runner, loaded, station_ft=60.0)
    assert "2 reading(s) on 2 location(s)" in call(runner, loaded, "list", NUMBER).output


def test_the_listing_can_be_narrowed_to_a_girder(runner: CliRunner, loaded: Path) -> None:
    add(runner, loaded, girder_id="G1")
    add(runner, loaded, girder_id="G2")
    result = call(runner, loaded, "list", NUMBER, "--girder", "G1")
    assert "G2" not in result.output
    assert "1 reading(s)" in result.output


def test_the_newest_flag_collapses_a_place_to_one_reading(runner: CliRunner, loaded: Path) -> None:
    add(runner, loaded, remaining_in=1.46, when="2019-04-02")
    add(runner, loaded, remaining_in=1.35, when="2026-04-02")
    everything = call(runner, loaded, "list", NUMBER)
    newest = call(runner, loaded, "list", NUMBER, "--newest")
    assert "2 reading(s)" in everything.output
    assert "1 reading(s)" in newest.output
    assert "1.460" not in newest.output


def test_the_loss_report_names_the_nominal_and_what_went(runner: CliRunner, loaded: Path) -> None:
    add(runner, loaded, remaining_in=1.20)
    result = call(runner, loaded, "loss", NUMBER, "G1")
    assert result.exit_code == 0, result.output
    assert "1.500 nominal" in result.output
    assert "0.300 lost" in result.output


def test_a_loss_over_a_tenth_is_a_finding(runner: CliRunner, loaded: Path) -> None:
    add(runner, loaded, remaining_in=1.30)
    assert "finding" in call(runner, loaded, "loss", NUMBER, "G1").output


def test_a_loss_over_a_quarter_is_severe(runner: CliRunner, loaded: Path) -> None:
    add(runner, loaded, remaining_in=1.00)
    assert "severe" in call(runner, loaded, "loss", NUMBER, "G1").output


def test_a_small_loss_is_only_a_note(runner: CliRunner, loaded: Path) -> None:
    add(runner, loaded, remaining_in=1.45)
    result = call(runner, loaded, "loss", NUMBER, "G1")
    assert "note" in result.output
    assert "severe" not in result.output


def test_the_loss_report_says_what_is_left_of_the_section(runner: CliRunner, loaded: Path) -> None:
    add(runner, loaded, remaining_in=1.20)
    assert "of nominal" in call(runner, loaded, "loss", NUMBER, "G1").output


def test_a_girder_with_no_readings_has_no_loss_report(runner: CliRunner, loaded: Path) -> None:
    add(runner, loaded, girder_id="G1")
    assert "no readings on G2" in call(runner, loaded, "loss", NUMBER, "G2").output


def test_a_place_measured_once_gives_no_rate(runner: CliRunner, loaded: Path) -> None:
    add(runner, loaded)
    result = call(runner, loaded, "rate", NUMBER)
    assert "none measured more than once" in result.output


def test_a_place_measured_twice_gives_a_rate(runner: CliRunner, loaded: Path) -> None:
    add(runner, loaded, remaining_in=1.46, when="2019-04-02")
    add(runner, loaded, remaining_in=1.32, when="2026-04-02")
    result = call(runner, loaded, "rate", NUMBER)
    assert "in/yr" in result.output
    assert "2 reading(s)" in result.output


def test_a_structure_with_no_readings_has_no_rates(runner: CliRunner, loaded: Path) -> None:
    assert "no readings" in call(runner, loaded, "rate", NUMBER).output


def test_rating_the_measured_sections_says_it_is_doing_so(runner: CliRunner, loaded: Path) -> None:
    add(runner, loaded, remaining_in=1.10)
    result = runner.invoke(
        main, ["--book", str(loaded), "rate", NUMBER, "--stations", "4", "--measured"]
    )
    assert result.exit_code == 0, result.output
    assert "with section loss from its readings" in result.output


def test_asking_for_measured_sections_with_none_says_so(runner: CliRunner, loaded: Path) -> None:
    # Not an error, and not silently the same thing either.
    result = runner.invoke(
        main, ["--book", str(loaded), "rate", NUMBER, "--stations", "4", "--measured"]
    )
    assert result.exit_code == 0
    assert "no thickness readings, rating the drawing sections" in result.output


def test_section_loss_lowers_the_rating(runner: CliRunner, loaded: Path) -> None:
    nominal = runner.invoke(main, ["--book", str(loaded), "rate", NUMBER, "--stations", "4"])
    add(runner, loaded, remaining_in=1.00, girder_id="G1")
    add(runner, loaded, remaining_in=1.00, girder_id="G2")
    add(runner, loaded, remaining_in=1.00, girder_id="G3")
    add(runner, loaded, remaining_in=1.00, girder_id="G4")
    measured = runner.invoke(
        main, ["--book", str(loaded), "rate", NUMBER, "--stations", "4", "--measured"]
    )
    assert _governing(measured) < _governing(nominal)


def test_section_loss_lowers_the_shear_rating(runner: CliRunner, loaded: Path) -> None:
    nominal = runner.invoke(main, ["--book", str(loaded), "shear", NUMBER, "--stations", "4"])
    for girder_id in ("G1", "G2", "G3", "G4"):
        add(runner, loaded, plate="web", remaining_in=0.375, girder_id=girder_id, station_ft=1.0)
    measured = runner.invoke(
        main, ["--book", str(loaded), "shear", NUMBER, "--stations", "4", "--measured"]
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
