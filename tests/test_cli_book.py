"""The book commands, and the two things standing between a prune and a delete."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from shearstud.cli import main
from shearstud.store import assessment as asm
from shearstud.store import db
from shearstud.store.assessment import StoredRating

pytestmark = pytest.mark.cli

NUMBER = "18-SH-0473"

#: Well outside the ten year retention policy, so a prune is allowed to run.
OLD = date.today() - timedelta(days=365 * 14)
OLDER = OLD - timedelta(days=365)
CUTOFF = (date.today() - timedelta(days=365 * 12)).isoformat()


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def add_rating(book: Path, when: date, vehicle: str = "TYPE3") -> None:
    asm.save_rating(
        book,
        StoredRating(
            structure_number=NUMBER,
            girder_id="G3",
            station_ft=60.0,
            limit_state="strength_i",
            level="operating",
            vehicle=vehicle,
            effect="moment",
            capacity=6000.0,
            factored_dead=1400.0,
            factored_live=3800.0,
            rating_factor=1.2,
            gross_weight_kip=50.0,
            rated_on=when,
        ),
    )


def call(runner: CliRunner, path: Path, *words: str) -> Result:
    return runner.invoke(main, ["--book", str(path), "book", *words])


def test_a_dry_run_removes_nothing(runner: CliRunner, seeded_book: Path) -> None:
    add_rating(seeded_book, OLDER)
    add_rating(seeded_book, OLD, vehicle="SU4")
    result = call(runner, seeded_book, "prune", "--before", CUTOFF)
    assert result.exit_code == 0, result.output
    assert "nothing removed, pass --yes to remove" in result.output
    assert db.row_count(seeded_book, "ratings") == 2


def test_a_dry_run_says_what_is_on_record(runner: CliRunner, seeded_book: Path) -> None:
    add_rating(seeded_book, OLDER)
    result = call(runner, seeded_book, "prune", "--before", CUTOFF)
    assert "ratings       1 row(s) on record" in result.output
    assert "evaluations   0 row(s) on record" in result.output


def test_saying_yes_removes_the_superseded_rows(runner: CliRunner, seeded_book: Path) -> None:
    add_rating(seeded_book, OLDER)
    add_rating(seeded_book, OLD, vehicle="SU4")
    result = call(runner, seeded_book, "prune", "--before", CUTOFF, "--yes")
    assert "ratings      1 removed" in result.output
    assert db.row_count(seeded_book, "ratings") == 1


def test_the_newest_run_survives_whatever_the_cutoff_says(
    runner: CliRunner, seeded_book: Path
) -> None:
    # A structure last rated fourteen years ago keeps its rating. Losing it
    # would leave a structure with no rating at all rather than an error.
    add_rating(seeded_book, OLDER)
    call(runner, seeded_book, "prune", "--before", CUTOFF, "--yes")
    assert db.row_count(seeded_book, "ratings") == 1


def test_a_prune_with_nothing_old_enough_says_so(runner: CliRunner, seeded_book: Path) -> None:
    result = call(runner, seeded_book, "prune", "--before", CUTOFF, "--yes")
    assert "nothing was old enough to remove" in result.output


def test_a_cutoff_inside_the_retention_policy_is_refused(
    runner: CliRunner, seeded_book: Path
) -> None:
    recent = (date.today() - timedelta(days=365)).isoformat()
    result = call(runner, seeded_book, "prune", "--before", recent, "--yes")
    assert result.exit_code != 0
    assert "retention policy" in result.output


def test_a_cutoff_inside_the_policy_is_refused_on_a_dry_run_too(
    runner: CliRunner, seeded_book: Path
) -> None:
    recent = (date.today() - timedelta(days=365)).isoformat()
    assert call(runner, seeded_book, "prune", "--before", recent).exit_code != 0


def test_a_cutoff_that_is_not_a_date_is_refused(runner: CliRunner, seeded_book: Path) -> None:
    assert call(runner, seeded_book, "prune", "--before", "ages ago").exit_code != 0


def test_the_prune_can_rebuild_the_file(runner: CliRunner, seeded_book: Path) -> None:
    add_rating(seeded_book, OLDER)
    add_rating(seeded_book, OLD, vehicle="SU4")
    result = call(runner, seeded_book, "prune", "--before", CUTOFF, "--yes", "--vacuum")
    assert "rebuilt the file" in result.output


def test_a_healthy_book_has_no_orphaned_spectra(runner: CliRunner, seeded_book: Path) -> None:
    result = call(runner, seeded_book, "orphans")
    assert result.exit_code == 0
    assert "no orphaned spectra" in result.output


def test_vacuum_reports_the_size_either_side(runner: CliRunner, seeded_book: Path) -> None:
    result = call(runner, seeded_book, "vacuum")
    assert result.exit_code == 0
    assert "bytes before" in result.output


def test_the_counts_name_every_table(runner: CliRunner, seeded_book: Path) -> None:
    result = call(runner, seeded_book, "counts")
    assert result.exit_code == 0
    for table in ("structures", "girders", "details", "ratings", "programme"):
        assert table in result.output


def test_the_counts_report_the_seeded_rows(runner: CliRunner, seeded_book: Path) -> None:
    result = call(runner, seeded_book, "counts")
    line = next(line for line in result.output.splitlines() if line.startswith("structures"))
    assert line.split()[-1] == "1"


def test_the_tables_the_prune_touches_are_the_ones_it_reports(
    runner: CliRunner, seeded_book: Path
) -> None:
    from shearstud.store import retention

    result = call(runner, seeded_book, "prune", "--before", CUTOFF)
    for table in retention.PRUNED_TABLES:
        assert table in result.output


def test_the_group_appears_in_the_help(runner: CliRunner) -> None:
    assert "book" in runner.invoke(main, ["--help"]).output
