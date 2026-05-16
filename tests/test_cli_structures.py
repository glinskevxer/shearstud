"""The inventory commands, driven through the runner the way a user drives
them."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from shearstud.cli import main
from shearstud.store import inventory
from tests.support import NUMBER

pytestmark = pytest.mark.cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def plate(label: str, width: float, height: float, y: float) -> dict[str, Any]:
    return {"label": label, "width_in": width, "height_in": height, "y_center_in": y}


def document(number: str = "18-SH-0473") -> dict[str, Any]:
    plates = [
        plate("bottom", 18.0, 1.5, 0.75),
        plate("web", 0.5625, 52.0, 27.5),
        plate("top", 16.0, 1.0, 54.0),
    ]
    return {
        "number": number,
        "name": "Salt Fork Creek",
        "year_built": 1968,
        "spans": [90.0],
        "girders": [
            {
                "girder_id": "G1",
                "girder_index": 0,
                "spacing_right_ft": 8.0,
                "overhang_ft": 3.5,
                "slab_thickness_in": 8.0,
                "haunch_in": 2.0,
                "runs": [
                    {
                        "from_station_ft": 0.0,
                        "to_station_ft": 90.0,
                        "label": "PG52",
                        "plates": plates,
                    }
                ],
                "details": [
                    {
                        "detail_id": "D1",
                        "kind": "cover_plate_end",
                        "category_name": "E",
                        "station_ft": 24.0,
                        "fibre": "bottom",
                    },
                    {
                        "detail_id": "D2",
                        "kind": "stiffener_weld",
                        "category_name": "E'",
                        "station_ft": 45.0,
                        "fibre": "web",
                    },
                ],
            },
            {
                "girder_id": "G2",
                "girder_index": 1,
                "spacing_left_ft": 8.0,
                "spacing_right_ft": 8.0,
                "slab_thickness_in": 8.0,
                "haunch_in": 2.0,
                "runs": [
                    {
                        "from_station_ft": 0.0,
                        "to_station_ft": 90.0,
                        "plates": plates,
                    }
                ],
            },
        ],
    }


def write_document(tmp_path: Path, number: str = "18-SH-0473") -> Path:
    path = tmp_path / f"{number}.json"
    path.write_text(json.dumps(document(number)), encoding="utf-8")
    return path


def imported(runner: CliRunner, book: Path, tmp_path: Path) -> Path:
    doc = write_document(tmp_path)
    result = runner.invoke(main, ["--book", str(book), "structure", "import", str(doc)])
    assert result.exit_code == 0, result.output
    return book


def test_an_empty_book_lists_nothing(runner: CliRunner, book: Path) -> None:
    result = runner.invoke(main, ["--book", str(book), "structure", "list"])
    assert result.exit_code == 0
    assert "no structures" in result.output


def test_importing_puts_a_structure_in_the_book(
    runner: CliRunner, book: Path, tmp_path: Path
) -> None:
    doc = write_document(tmp_path)
    result = runner.invoke(main, ["--book", str(book), "structure", "import", str(doc)])
    assert result.exit_code == 0
    assert "imported 18-SH-0473 with 2 girders" in result.output
    assert inventory.exists(book, "18-SH-0473")


def test_the_policy_options_reach_the_book(runner: CliRunner, book: Path, tmp_path: Path) -> None:
    from shearstud.store import db

    doc = write_document(tmp_path)
    runner.invoke(
        main,
        [
            "--book",
            str(book),
            "structure",
            "import",
            str(doc),
            "--grade",
            "A572-50",
            "--condition",
            "fair",
            "--adtt",
            "2400",
        ],
    )
    row = db.fetch_one(book, "SELECT steel_grade, adtt FROM structures")
    assert row is not None
    assert row["steel_grade"] == "A572-50"
    assert row["adtt"] == pytest.approx(2400.0)


def test_importing_twice_is_refused_without_force(
    runner: CliRunner, book: Path, tmp_path: Path
) -> None:
    doc = write_document(tmp_path)
    runner.invoke(main, ["--book", str(book), "structure", "import", str(doc)])
    result = runner.invoke(main, ["--book", str(book), "structure", "import", str(doc)])
    assert result.exit_code != 0
    assert "--force" in result.output


def test_force_replaces_what_is_there(runner: CliRunner, book: Path, tmp_path: Path) -> None:
    doc = write_document(tmp_path)
    runner.invoke(main, ["--book", str(book), "structure", "import", str(doc)])
    result = runner.invoke(main, ["--book", str(book), "structure", "import", str(doc), "--force"])
    assert result.exit_code == 0
    assert len(inventory.numbers(book)) == 1


def test_a_bad_document_is_reported_not_traced(
    runner: CliRunner, book: Path, tmp_path: Path
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"number": "18-SH-0473"}', encoding="utf-8")
    result = runner.invoke(main, ["--book", str(book), "structure", "import", str(bad)])
    assert result.exit_code != 0


def test_listing_shows_the_structure(runner: CliRunner, book: Path, tmp_path: Path) -> None:
    imported(runner, book, tmp_path)
    result = runner.invoke(main, ["--book", str(book), "structure", "list"])
    assert "18-SH-0473" in result.output
    assert "Salt Fork Creek" in result.output
    assert "2 girders" in result.output


def test_showing_gives_the_summary(runner: CliRunner, book: Path, tmp_path: Path) -> None:
    imported(runner, book, tmp_path)
    result = runner.invoke(main, ["--book", str(book), "structure", "show", "18-SH-0473"])
    assert result.exit_code == 0
    assert "Salt Fork Creek" in result.output
    assert "1968" in result.output
    assert "simple" in result.output
    assert "details  2" in result.output


def test_showing_lists_the_girders(runner: CliRunner, book: Path, tmp_path: Path) -> None:
    imported(runner, book, tmp_path)
    result = runner.invoke(main, ["--book", str(book), "structure", "show", "18-SH-0473"])
    assert "G1" in result.output
    assert "exterior" in result.output
    assert "interior" in result.output


def test_the_girder_list_can_be_turned_off(runner: CliRunner, book: Path, tmp_path: Path) -> None:
    imported(runner, book, tmp_path)
    result = runner.invoke(
        main, ["--book", str(book), "structure", "show", "18-SH-0473", "--no-girders"]
    )
    assert "exterior" not in result.output


def test_showing_a_structure_that_is_not_there_is_reported(runner: CliRunner, book: Path) -> None:
    result = runner.invoke(main, ["--book", str(book), "structure", "show", "99-IH-0001"])
    assert result.exit_code != 0


def test_exporting_writes_a_document_that_reads_back(
    runner: CliRunner, book: Path, tmp_path: Path
) -> None:
    imported(runner, book, tmp_path)
    out = tmp_path / "out.json"
    result = runner.invoke(
        main, ["--book", str(book), "structure", "export", "18-SH-0473", str(out)]
    )
    assert result.exit_code == 0
    assert out.exists()
    again = json.loads(out.read_text(encoding="utf-8"))
    assert again["number"] == "18-SH-0473"


def test_the_export_round_trips_through_an_import(
    runner: CliRunner, book: Path, tmp_path: Path
) -> None:
    imported(runner, book, tmp_path)
    out = tmp_path / "out.json"
    runner.invoke(main, ["--book", str(book), "structure", "export", "18-SH-0473", str(out)])
    runner.invoke(main, ["--book", str(book), "structure", "delete", "18-SH-0473", "--yes"])
    result = runner.invoke(main, ["--book", str(book), "structure", "import", str(out)])
    assert result.exit_code == 0
    assert inventory.exists(book, "18-SH-0473")


def test_deleting_asks_first(runner: CliRunner, book: Path, tmp_path: Path) -> None:
    imported(runner, book, tmp_path)
    result = runner.invoke(
        main, ["--book", str(book), "structure", "delete", "18-SH-0473"], input="n\n"
    )
    assert result.exit_code != 0
    assert inventory.exists(book, "18-SH-0473")


def test_deleting_with_yes_does_not_ask(runner: CliRunner, book: Path, tmp_path: Path) -> None:
    imported(runner, book, tmp_path)
    result = runner.invoke(
        main, ["--book", str(book), "structure", "delete", "18-SH-0473", "--yes"]
    )
    assert result.exit_code == 0
    assert not inventory.exists(book, "18-SH-0473")


def test_deleting_something_that_is_not_there_is_reported(runner: CliRunner, book: Path) -> None:
    result = runner.invoke(
        main, ["--book", str(book), "structure", "delete", "99-IH-0001", "--yes"]
    )
    assert result.exit_code != 0
    assert "no structure" in result.output


def test_the_details_command_lists_every_detail(
    runner: CliRunner, book: Path, tmp_path: Path
) -> None:
    imported(runner, book, tmp_path)
    result = runner.invoke(main, ["--book", str(book), "structure", "details", "18-SH-0473"])
    assert result.exit_code == 0
    assert "D1" in result.output
    assert "D2" in result.output


def test_the_details_command_flags_a_downgraded_detail(
    runner: CliRunner, book: Path, tmp_path: Path
) -> None:
    imported(runner, book, tmp_path)
    result = runner.invoke(main, ["--book", str(book), "structure", "details", "18-SH-0473"])
    lines = [line for line in result.output.splitlines() if line.startswith("D2")]
    assert lines and "downgraded" in lines[0]


def test_the_details_can_be_ordered_worst_first(
    runner: CliRunner, book: Path, tmp_path: Path
) -> None:
    imported(runner, book, tmp_path)
    result = runner.invoke(
        main, ["--book", str(book), "structure", "details", "18-SH-0473", "--worst-first"]
    )
    lines = [line for line in result.output.splitlines() if line.startswith("D")]
    assert lines[0].startswith("D2")


def test_a_structure_with_no_details_says_so(runner: CliRunner, book: Path, tmp_path: Path) -> None:
    doc = document("07-CR-1204")
    doc["girders"][0].pop("details")
    path = tmp_path / "bare.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    runner.invoke(main, ["--book", str(book), "structure", "import", str(path)])
    result = runner.invoke(main, ["--book", str(book), "structure", "details", "07-CR-1204"])
    assert "no details" in result.output


@pytest.fixture
def imported_book(runner: CliRunner, book: Path, tmp_path: Path) -> Path:
    """A book holding the four girder structure the section tests read."""
    return imported(runner, book, tmp_path)


def section_call(runner: CliRunner, book: Path, *extra: str) -> Any:
    argv = [
        "--book",
        str(book),
        "structure",
        "section",
        NUMBER,
        "G1",
        "--station-ft",
        "45",
        *extra,
    ]
    return runner.invoke(main, argv)


def test_the_section_command_names_the_run_it_is_in(runner: CliRunner, imported_book: Path) -> None:
    result = section_call(runner, imported_book)
    assert result.exit_code == 0, result.output
    assert "in the run from 0 to 90 ft" in result.output


def test_the_section_command_lists_the_plates(runner: CliRunner, imported_book: Path) -> None:
    result = section_call(runner, imported_book)
    for label in ("bottom", "web", "top"):
        assert label in result.output


def test_the_section_command_reports_three_stages(runner: CliRunner, imported_book: Path) -> None:
    # A composite girder has a different section for the dead load it carried
    # before the deck cured, for the sustained load afterwards, and for a
    # truck. Reporting one of them is how a dead load stress gets worked out
    # on a section that did not exist yet.
    result = section_call(runner, imported_book)
    for stage in ("noncomposite", "long term", "short term"):
        assert stage in result.output


def test_the_composite_stages_get_stiffer_in_order(runner: CliRunner, imported_book: Path) -> None:
    result = section_call(runner, imported_book)
    inertias = [
        float(line.split("I")[1].split()[0])
        for line in result.output.splitlines()
        if line.startswith(("noncomposite", "long term", "short term"))
    ]
    assert inertias == sorted(inertias)


def test_the_steel_only_flag_reports_one_section(runner: CliRunner, imported_book: Path) -> None:
    result = section_call(runner, imported_book, "--steel-only")
    assert "steel " in result.output
    assert "short term" not in result.output


def test_the_section_command_says_where_the_numbers_came_from(
    runner: CliRunner, imported_book: Path
) -> None:
    assert "source   the drawing" in section_call(runner, imported_book).output
    assert "measured sections" in section_call(runner, imported_book, "--measured").output


def test_a_thickness_reading_shows_up_in_the_measured_section(
    runner: CliRunner, imported_book: Path
) -> None:
    runner.invoke(
        main,
        [
            "--book",
            str(imported_book),
            "thickness",
            "add",
            NUMBER,
            "G1",
            "bottom",
            "--station-ft",
            "45",
            "--remaining-in",
            "1.10",
            "--measured",
            "2026-04-02",
        ],
    )
    nominal = section_call(runner, imported_book)
    reduced = section_call(runner, imported_book, "--measured")
    assert _inertia(reduced, "short term") < _inertia(nominal, "short term")


def test_a_station_past_the_end_is_refused(runner: CliRunner, imported_book: Path) -> None:
    result = runner.invoke(
        main,
        [
            "--book",
            str(imported_book),
            "structure",
            "section",
            NUMBER,
            "G1",
            "--station-ft",
            "500",
        ],
    )
    assert result.exit_code != 0
    assert "past the end" in result.output


def test_a_girder_that_is_not_there_is_refused(runner: CliRunner, imported_book: Path) -> None:
    result = runner.invoke(
        main,
        [
            "--book",
            str(imported_book),
            "structure",
            "section",
            NUMBER,
            "G9",
            "--station-ft",
            "45",
        ],
    )
    assert result.exit_code != 0


def _inertia(result: Any, stage: str) -> float:
    line = next(line for line in result.output.splitlines() if line.startswith(stage))
    return float(line.split("I")[1].split()[0])
