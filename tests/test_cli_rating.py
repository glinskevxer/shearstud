"""The rating and posting commands, including the opt in to writing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from shearstud.cli import main
from shearstud.store import assessment as asm

pytestmark = pytest.mark.cli

NUMBER = "18-SH-0473"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def plate(label: str, width: float, height: float, y: float) -> dict[str, Any]:
    return {"label": label, "width_in": width, "height_in": height, "y_center_in": y}


def document(bottom_in: float = 1.5) -> dict[str, Any]:
    plates = [
        plate("bottom", 18.0, bottom_in, bottom_in / 2.0),
        plate("web", 0.5625, 52.0, bottom_in + 26.0),
        plate("top", 16.0, 1.0, bottom_in + 52.5),
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
                "runs": [
                    {
                        "from_station_ft": 0.0,
                        "to_station_ft": 90.0,
                        "label": "PG52",
                        "plates": plates,
                    }
                ],
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
def rated_book(runner: CliRunner, book: Path, tmp_path: Path) -> Path:
    path = tmp_path / "structure.json"
    path.write_text(json.dumps(document()), encoding="utf-8")
    result = runner.invoke(
        main,
        ["--book", str(book), "structure", "import", str(path), "--adtt", "1200", "--grade", "A36"],
    )
    assert result.exit_code == 0, result.output
    return book


def test_rating_prints_a_governing_factor(runner: CliRunner, rated_book: Path) -> None:
    result = runner.invoke(main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4"])
    assert result.exit_code == 0, result.output
    assert "governing RF" in result.output


def test_rating_says_whether_the_structure_is_adequate(runner: CliRunner, rated_book: Path) -> None:
    result = runner.invoke(main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4"])
    assert "adequate" in result.output.lower()


def test_the_verbose_flag_prints_every_station(runner: CliRunner, rated_book: Path) -> None:
    quiet = runner.invoke(main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4"])
    loud = runner.invoke(
        main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4", "--verbose"]
    )
    assert len(loud.output.splitlines()) > len(quiet.output.splitlines())
    assert "df " in loud.output


def test_rating_writes_nothing_by_default(runner: CliRunner, rated_book: Path) -> None:
    runner.invoke(main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4"])
    assert asm.load_ratings(rated_book, NUMBER) == []


def test_save_writes_the_results(runner: CliRunner, rated_book: Path) -> None:
    result = runner.invoke(
        main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4", "--save"]
    )
    assert result.exit_code == 0
    assert "saved" in result.output
    assert asm.load_ratings(rated_book, NUMBER)


def test_the_saved_rows_carry_the_vehicles(runner: CliRunner, rated_book: Path) -> None:
    runner.invoke(main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4", "--save"])
    saved = asm.load_ratings(rated_book, NUMBER)
    assert "TYPE3" in {row.vehicle for row in saved}


def test_the_design_load_rates_at_inventory(runner: CliRunner, rated_book: Path) -> None:
    result = runner.invoke(
        main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4", "--design"]
    )
    assert result.exit_code == 0
    assert "inventory" in result.output


def test_an_overlay_lowers_the_printed_factor(runner: CliRunner, rated_book: Path) -> None:
    bare = runner.invoke(main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4"])
    paved = runner.invoke(
        main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4", "--overlay", "5"]
    )
    assert _factor(bare.output) > _factor(paved.output)


def test_a_rough_surface_lowers_the_printed_factor(runner: CliRunner, rated_book: Path) -> None:
    smooth = runner.invoke(
        main,
        ["--book", str(rated_book), "rate", NUMBER, "--stations", "4", "--surface", "smooth"],
    )
    rough = runner.invoke(
        main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4", "--surface", "rough"]
    )
    assert _factor(smooth.output) > _factor(rough.output)


def test_overriding_the_condition_lowers_the_factor(runner: CliRunner, rated_book: Path) -> None:
    good = runner.invoke(main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4"])
    poor = runner.invoke(
        main,
        ["--book", str(rated_book), "rate", NUMBER, "--stations", "4", "--condition", "poor"],
    )
    assert _factor(poor.output) < _factor(good.output)


def _factor(output: str) -> float:
    for line in output.splitlines():
        if "governing RF" in line:
            return float(line.split("governing RF")[1].split()[0])
    raise AssertionError(f"no governing factor in:\n{output}")


def test_an_unknown_surface_is_refused(runner: CliRunner, rated_book: Path) -> None:
    result = runner.invoke(main, ["--book", str(rated_book), "rate", NUMBER, "--surface", "gravel"])
    assert result.exit_code != 0


def test_rating_a_structure_that_is_not_there_is_reported(runner: CliRunner, book: Path) -> None:
    result = runner.invoke(main, ["--book", str(book), "rate", "99-IH-0001"])
    assert result.exit_code != 0


def test_the_posting_command_gives_an_outcome(runner: CliRunner, rated_book: Path) -> None:
    result = runner.invoke(main, ["--book", str(rated_book), "posting", NUMBER, "--stations", "4"])
    assert result.exit_code == 0, result.output
    assert any(word in result.output for word in ("open", "posted", "closed"))


def test_a_healthy_structure_needs_no_sign(runner: CliRunner, rated_book: Path) -> None:
    result = runner.invoke(main, ["--book", str(rated_book), "posting", NUMBER, "--stations", "4"])
    assert "no sign needed" in result.output


def test_a_thick_overlay_can_post_the_structure(runner: CliRunner, rated_book: Path) -> None:
    result = runner.invoke(
        main,
        ["--book", str(rated_book), "posting", NUMBER, "--stations", "4", "--overlay", "24"],
    )
    assert result.exit_code == 0
    assert "TONS" in result.output or "closed" in result.output


def test_the_posting_writes_nothing_by_default(runner: CliRunner, rated_book: Path) -> None:
    runner.invoke(main, ["--book", str(rated_book), "posting", NUMBER, "--stations", "4"])
    assert asm.current_outcome(rated_book, NUMBER) is None


def test_saving_the_posting_records_the_outcome(runner: CliRunner, rated_book: Path) -> None:
    runner.invoke(main, ["--book", str(rated_book), "posting", NUMBER, "--stations", "4", "--save"])
    assert asm.current_outcome(rated_book, NUMBER) is not None


def test_the_ratings_command_says_when_there_are_none(runner: CliRunner, rated_book: Path) -> None:
    result = runner.invoke(main, ["--book", str(rated_book), "ratings", NUMBER])
    assert "never been rated" in result.output


def test_the_ratings_command_lists_what_was_saved(runner: CliRunner, rated_book: Path) -> None:
    runner.invoke(main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4", "--save"])
    result = runner.invoke(main, ["--book", str(rated_book), "ratings", NUMBER])
    assert result.exit_code == 0
    assert "RF" in result.output


def test_the_ratings_command_caps_its_output(runner: CliRunner, rated_book: Path) -> None:
    runner.invoke(main, ["--book", str(rated_book), "rate", NUMBER, "--stations", "4", "--save"])
    result = runner.invoke(main, ["--book", str(rated_book), "ratings", NUMBER, "--limit", "3"])
    assert "and " in result.output
    assert "more" in result.output


def shear(runner: CliRunner, book: Path, *extra: str) -> Any:
    argv = ["--book", str(book), "shear", NUMBER, "--stations", "4", *extra]
    return runner.invoke(main, argv)


def test_the_shear_command_prints_a_governing_factor(runner: CliRunner, rated_book: Path) -> None:
    result = shear(runner, rated_book)
    assert result.exit_code == 0, result.output
    assert "governing shear RF" in result.output


def test_the_shear_command_says_whether_the_web_is_adequate(
    runner: CliRunner, rated_book: Path
) -> None:
    assert "in shear" in shear(runner, rated_book).output


def test_the_shear_command_is_quiet_by_default(runner: CliRunner, rated_book: Path) -> None:
    assert len(shear(runner, rated_book).output.strip().splitlines()) == 2


def test_the_verbose_flag_prints_every_shear_station(runner: CliRunner, rated_book: Path) -> None:
    quiet = shear(runner, rated_book)
    loud = shear(runner, rated_book, "--verbose")
    assert len(loud.output.splitlines()) > len(quiet.output.splitlines())
    assert "D/tw" in loud.output


def test_the_ends_only_flag_prints_the_ends(runner: CliRunner, rated_book: Path) -> None:
    result = shear(runner, rated_book, "--ends-only")
    listed = [line for line in result.output.splitlines() if "RF" in line and "D/tw" in line]
    # Four girders, two ends each.
    assert len(listed) == 8


def test_the_ends_only_flag_prints_fewer_lines_than_verbose(
    runner: CliRunner, rated_book: Path
) -> None:
    ends = shear(runner, rated_book, "--ends-only")
    loud = shear(runner, rated_book, "--verbose")
    assert len(ends.output.splitlines()) < len(loud.output.splitlines())


def test_the_shear_command_writes_nothing_unless_asked(runner: CliRunner, rated_book: Path) -> None:
    shear(runner, rated_book)
    assert asm.load_ratings(rated_book, NUMBER) == []


def test_the_shear_command_saves_when_asked(runner: CliRunner, rated_book: Path) -> None:
    result = shear(runner, rated_book, "--save")
    assert "saved" in result.output
    stored = asm.load_ratings(rated_book, NUMBER)
    assert stored
    assert {row.effect for row in stored} == {"shear"}


def test_a_thicker_overlay_lowers_the_shear_rating(runner: CliRunner, rated_book: Path) -> None:
    thin = shear(runner, rated_book, "--overlay", "0")
    thick = shear(runner, rated_book, "--overlay", "6")
    assert _governing(thick) < _governing(thin)


def test_a_rough_surface_lowers_the_shear_rating(runner: CliRunner, rated_book: Path) -> None:
    smooth = shear(runner, rated_book, "--surface", "smooth")
    rough = shear(runner, rated_book, "--surface", "rough")
    assert _governing(rough) < _governing(smooth)


def test_a_worse_condition_lowers_the_shear_rating(runner: CliRunner, rated_book: Path) -> None:
    good = shear(runner, rated_book, "--condition", "good")
    poor = shear(runner, rated_book, "--condition", "poor")
    assert _governing(poor) < _governing(good)


def test_a_structure_that_is_not_in_the_book_is_refused(runner: CliRunner, book: Path) -> None:
    assert shear(runner, book).exit_code != 0


def _governing(result: Any) -> float:
    """The factor off a shear command's summary line."""
    line = next(line for line in result.output.splitlines() if "governing shear RF" in line)
    return float(line.split("governing shear RF")[1].split()[0])
