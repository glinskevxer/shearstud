"""The report commands, and the silences flag that is the shortest useful one."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from shearstud.cli import main
from shearstud.store import assessment as asm
from shearstud.store import programme as prog
from shearstud.store.assessment import StoredRating
from shearstud.store.programme import ProgrammeRow

pytestmark = pytest.mark.cli

NUMBER = "18-SH-0473"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def add_programme(book: Path, rating: int = 8, inspected: date = date(2025, 4, 2)) -> None:
    prog.save(
        book,
        ProgrammeRow(
            structure_number=NUMBER,
            lowest_condition_rating=rating,
            daily_traffic=3400,
            detour_mi=8.5,
            is_posted=False,
            last_inspected=inspected,
            updated_on=inspected,
        ),
    )


def add_rating(book: Path, factor: float = 1.35) -> None:
    asm.save_rating(
        book,
        StoredRating(
            structure_number=NUMBER,
            girder_id="G3",
            station_ft=60.0,
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


def report(runner: CliRunner, book: Path, *words: str) -> Result:
    return runner.invoke(main, ["--book", str(book), "report", *words])


def test_a_structure_report_prints_its_identity(runner: CliRunner, seeded_book: Path) -> None:
    result = report(runner, seeded_book, "structure", NUMBER)
    assert result.exit_code == 0, result.output
    assert NUMBER in result.output
    assert "Salt Fork Creek" in result.output


def test_a_structure_report_counts_the_silences(runner: CliRunner, seeded_book: Path) -> None:
    result = report(runner, seeded_book, "structure", NUMBER)
    assert "4 of 10 lines have nothing behind them" in result.output


def test_the_silences_flag_prints_only_the_absences(runner: CliRunner, seeded_book: Path) -> None:
    result = report(runner, seeded_book, "structure", NUMBER, "--silences")
    assert result.exit_code == 0
    assert len(result.output.strip().splitlines()) == 4
    assert "nothing on record" in result.output
    assert "Salt Fork Creek" not in result.output


def test_the_silences_flag_says_so_when_nothing_is_missing(
    runner: CliRunner, seeded_book: Path
) -> None:
    add_programme(seeded_book)
    add_rating(seeded_book)
    # Still missing a posting and a measurement, so plant those too.
    result = report(runner, seeded_book, "structure", NUMBER, "--silences")
    assert "nothing on record" in result.output


def test_a_report_for_a_structure_that_is_not_there_is_refused(
    runner: CliRunner, seeded_book: Path
) -> None:
    result = report(runner, seeded_book, "structure", "99-XX-9999")
    assert result.exit_code != 0
    assert "no structure" in result.output


def test_the_inventory_report_counts_the_structures(runner: CliRunner, seeded_book: Path) -> None:
    result = report(runner, seeded_book, "inventory")
    assert result.exit_code == 0, result.output
    assert "structures  1" in result.output


def test_the_inventory_report_names_the_bands(runner: CliRunner, seeded_book: Path) -> None:
    result = report(runner, seeded_book, "inventory")
    for band in ("restricted", "retrofit", "preserve", "monitor"):
        assert band in result.output


def test_the_inventory_report_takes_a_date(runner: CliRunner, seeded_book: Path) -> None:
    add_programme(seeded_book, inspected=date(2019, 4, 1))
    early = report(runner, seeded_book, "inventory", "--on", "2019-05-01")
    late = report(runner, seeded_book, "inventory", "--on", "2026-05-01")
    assert "overdue     none" in early.output
    assert "overdue     1" in late.output


def test_a_date_that_is_not_a_date_is_refused(runner: CliRunner, seeded_book: Path) -> None:
    assert report(runner, seeded_book, "inventory", "--on", "last tuesday").exit_code != 0


def test_the_overdue_report_says_when_nothing_is_due(runner: CliRunner, seeded_book: Path) -> None:
    assert "nothing overdue" in report(runner, seeded_book, "overdue").output


def test_the_overdue_report_lists_what_is_due(runner: CliRunner, seeded_book: Path) -> None:
    add_programme(seeded_book, inspected=date(2019, 4, 1))
    result = report(runner, seeded_book, "overdue", "--on", "2026-05-01")
    assert NUMBER in result.output
    assert "1 overdue" in result.output


def test_the_overdue_report_names_the_interval(runner: CliRunner, seeded_book: Path) -> None:
    add_programme(seeded_book, rating=3, inspected=date(2019, 4, 1))
    result = report(runner, seeded_book, "overdue", "--on", "2026-05-01")
    assert "on a 12 month interval" in result.output


def test_the_overdue_report_defaults_to_today(runner: CliRunner, seeded_book: Path) -> None:
    add_programme(seeded_book, inspected=date(2001, 4, 1))
    assert NUMBER in report(runner, seeded_book, "overdue").output


def test_an_empty_book_reports_an_empty_inventory(runner: CliRunner, book: Path) -> None:
    result = report(runner, book, "inventory")
    assert "structures  0" in result.output


def test_the_group_appears_in_the_help(runner: CliRunner) -> None:
    assert "report" in runner.invoke(main, ["--help"]).output
