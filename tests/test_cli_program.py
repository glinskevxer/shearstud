"""The programme commands, and the order the worklist prints things in."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from shearstud.cli import main
from shearstud.store import assessment as asm
from shearstud.store import db
from shearstud.store.assessment import StoredRating
from tests import support

pytestmark = pytest.mark.cli

NUMBER = "18-SH-0473"
OTHER = "07-CR-0112"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def add_structure(book: Path, number: str, redundancy: str = "redundant") -> None:
    db.execute(
        book,
        support.insert_structure_sql(),
        support.structure_row(
            number,
            name="A bridge",
            county_code=7,
            route_class="CR",
            sequence=112,
            redundancy=redundancy,
            year_built=1962,
            span_lengths_ft="[84.0]",
        ),
    )


def add_rating(book: Path, number: str = NUMBER, factor: float = 1.35) -> None:
    asm.save_rating(
        book,
        StoredRating(
            structure_number=number,
            girder_id="G2",
            station_ft=42.0,
            limit_state="strength_i",
            level="operating",
            vehicle="TYPE3",
            effect="moment",
            capacity=6000.0,
            factored_dead=1400.0,
            factored_live=3800.0,
            rating_factor=factor,
            gross_weight_kip=50.0,
            rated_on=date(2025, 6, 1),
        ),
    )


def record(
    runner: CliRunner,
    book: Path,
    number: str = NUMBER,
    condition: int = 8,
    inspected: str = "2025-04-02",
    extra: list[str] | None = None,
) -> Result:
    argv = [
        "--book",
        str(book),
        "program",
        "record",
        number,
        "--condition",
        str(condition),
        "--inspected",
        inspected,
        *(extra or []),
    ]
    return runner.invoke(main, argv)


def test_an_inspection_is_recorded(runner: CliRunner, seeded_book: Path) -> None:
    result = record(runner, seeded_book)
    assert result.exit_code == 0, result.output
    assert "recorded 18-SH-0473 at condition 8" in result.output


def test_the_traffic_and_detour_are_kept(runner: CliRunner, seeded_book: Path) -> None:
    record(runner, seeded_book, extra=["--traffic", "3400", "--detour-mi", "8.5"])
    result = runner.invoke(main, ["--book", str(seeded_book), "program", "show", NUMBER])
    assert "3400 a day over 8.5 miles" in result.output


def test_recording_again_replaces_the_row(runner: CliRunner, seeded_book: Path) -> None:
    record(runner, seeded_book, condition=8)
    record(runner, seeded_book, condition=4)
    assert db.row_count(seeded_book, "programme") == 1
    result = runner.invoke(main, ["--book", str(seeded_book), "program", "show", NUMBER])
    assert "condition  4" in result.output


def test_a_condition_rating_off_the_scale_is_refused(runner: CliRunner, seeded_book: Path) -> None:
    assert record(runner, seeded_book, condition=11).exit_code != 0


def test_a_structure_that_is_not_in_the_book_is_refused(
    runner: CliRunner, seeded_book: Path
) -> None:
    assert record(runner, seeded_book, number="99-XX-9999").exit_code != 0


def test_showing_a_structure_nobody_inspected_is_refused(
    runner: CliRunner, seeded_book: Path
) -> None:
    result = runner.invoke(main, ["--book", str(seeded_book), "program", "show", NUMBER])
    assert result.exit_code != 0
    assert "no programme row" in result.output


def test_the_show_gives_the_interval_and_the_due_date(runner: CliRunner, seeded_book: Path) -> None:
    record(runner, seeded_book, condition=8)
    result = runner.invoke(main, ["--book", str(seeded_book), "program", "show", NUMBER])
    assert "interval   48 months" in result.output
    assert "next due   2029-" in result.output


def test_a_poor_rating_shows_the_short_interval(runner: CliRunner, seeded_book: Path) -> None:
    record(runner, seeded_book, condition=3)
    result = runner.invoke(main, ["--book", str(seeded_book), "program", "show", NUMBER])
    assert "interval   12 months" in result.output
    assert "shortened by condition" in result.output


def test_the_show_says_when_the_life_was_credited_rather_than_measured(
    runner: CliRunner, seeded_book: Path
) -> None:
    record(runner, seeded_book)
    result = runner.invoke(main, ["--book", str(seeded_book), "program", "show", NUMBER])
    assert "no measurement, credited" in result.output


def test_the_worklist_prints_the_gaps_before_the_ranking(
    runner: CliRunner, seeded_book: Path
) -> None:
    result = runner.invoke(main, ["--book", str(seeded_book), "program", "worklist"])
    assert result.exit_code == 0, result.output
    assert "never inspected under this programme" in result.output
    assert NUMBER in result.output


def test_a_structure_with_no_rating_is_named_as_a_gap(runner: CliRunner, seeded_book: Path) -> None:
    record(runner, seeded_book)
    result = runner.invoke(main, ["--book", str(seeded_book), "program", "worklist"])
    assert "no load rating on record" in result.output


def test_a_ranked_structure_prints_its_band_and_its_reason(
    runner: CliRunner, seeded_book: Path
) -> None:
    record(runner, seeded_book)
    add_rating(seeded_book)
    result = runner.invoke(main, ["--book", str(seeded_book), "program", "worklist"])
    assert "monitor" in result.output
    assert "1 of 1 structures ranked (100%)" in result.output


def test_a_restricted_structure_prints_its_rating_factor(
    runner: CliRunner, seeded_book: Path
) -> None:
    record(runner, seeded_book)
    add_rating(seeded_book, factor=0.86)
    result = runner.invoke(main, ["--book", str(seeded_book), "program", "worklist"])
    assert "restricted" in result.output
    assert "0.86" in result.output


def test_the_worklist_says_which_structures_ran_on_a_credited_life(
    runner: CliRunner, seeded_book: Path
) -> None:
    record(runner, seeded_book)
    add_rating(seeded_book)
    result = runner.invoke(main, ["--book", str(seeded_book), "program", "worklist"])
    assert "ranked on a credited life" in result.output


def test_the_worklist_can_be_cut_to_one_band(runner: CliRunner, seeded_book: Path) -> None:
    add_structure(seeded_book, OTHER)
    record(runner, seeded_book)
    add_rating(seeded_book)
    record(runner, seeded_book, number=OTHER, condition=8)
    add_rating(seeded_book, number=OTHER, factor=0.7)
    result = runner.invoke(
        main, ["--book", str(seeded_book), "program", "worklist", "--band", "restricted"]
    )
    assert OTHER in result.output
    assert NUMBER not in result.output.split("structures ranked")[0].split("\n", 1)[1]


def test_an_unknown_band_is_refused(runner: CliRunner, seeded_book: Path) -> None:
    result = runner.invoke(
        main, ["--book", str(seeded_book), "program", "worklist", "--band", "urgent"]
    )
    assert result.exit_code != 0
    assert "unknown band" in result.output


def test_the_worklist_can_be_cut_to_a_length(runner: CliRunner, seeded_book: Path) -> None:
    add_structure(seeded_book, OTHER)
    for number in (NUMBER, OTHER):
        record(runner, seeded_book, number=number)
        add_rating(seeded_book, number=number)
    result = runner.invoke(
        main, ["--book", str(seeded_book), "program", "worklist", "--limit", "1"]
    )
    listed = [line for line in result.output.splitlines() if "monitor" in line]
    assert len(listed) == 1


def test_an_empty_book_ranks_nothing(runner: CliRunner, book: Path) -> None:
    result = runner.invoke(main, ["--book", str(book), "program", "worklist"])
    assert "nothing ranked" in result.output


def test_nothing_is_overdue_the_day_after_an_inspection(
    runner: CliRunner, seeded_book: Path
) -> None:
    record(runner, seeded_book, inspected="2025-04-02")
    result = runner.invoke(
        main, ["--book", str(seeded_book), "program", "due", "--on", "2025-04-03"]
    )
    assert "nothing overdue" in result.output


def test_a_structure_past_its_interval_is_listed(runner: CliRunner, seeded_book: Path) -> None:
    record(runner, seeded_book, inspected="2019-04-02")
    result = runner.invoke(
        main, ["--book", str(seeded_book), "program", "due", "--on", "2026-04-03"]
    )
    assert NUMBER in result.output
    assert "1 overdue" in result.output


def test_the_due_list_names_the_interval_it_used(runner: CliRunner, seeded_book: Path) -> None:
    record(runner, seeded_book, condition=3, inspected="2019-04-02")
    result = runner.invoke(
        main, ["--book", str(seeded_book), "program", "due", "--on", "2026-04-03"]
    )
    assert "on a 12 month interval" in result.output


def test_the_due_list_defaults_to_today(runner: CliRunner, seeded_book: Path) -> None:
    record(runner, seeded_book, inspected="2001-04-02")
    result = runner.invoke(main, ["--book", str(seeded_book), "program", "due"])
    assert NUMBER in result.output


def test_a_book_with_no_programme_rows_has_nothing_overdue(runner: CliRunner, book: Path) -> None:
    result = runner.invoke(main, ["--book", str(book), "program", "due"])
    assert "nothing overdue" in result.output


def test_the_group_appears_in_the_help(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--help"])
    assert "program" in result.output
