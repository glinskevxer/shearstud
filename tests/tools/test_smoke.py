"""The end to end run, which says the pieces fit rather than that each is right.

The run is done once for the whole module and every question is asked of that
one result. It rates thirty six stations against the legal fleet and then does
it again per posting silhouette, which takes about eleven seconds, and asking
fifteen questions used to mean paying for it fifteen times. Where a test needs
a book nobody else has touched it makes its own and says why.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from shearstud.program import interval
from shearstud.store import db, importer
from shearstud.tools import smoke

pytestmark = pytest.mark.tools


@dataclass(frozen=True, slots=True)
class Run:
    """One smoke run: what it printed, and the book it left."""

    lines: list[str]
    book: Path

    def step(self, name: str) -> str:
        """The line one step produced."""
        return next(line for line in self.lines if line.startswith(name))


@pytest.fixture(scope="module")
def smoke_run(tmp_path_factory: pytest.TempPathFactory) -> Run:
    """One run, shared by every test that only wants to read the result."""
    book = tmp_path_factory.mktemp("smoke") / "smoke.sqlite3"
    return Run(lines=smoke.run(book), book=book)


def test_the_example_document_is_where_it_says_it_is() -> None:
    assert smoke.EXAMPLE.exists()
    assert smoke.EXAMPLE.name.endswith(".json")


def test_the_example_document_reads() -> None:
    structure = importer.read(smoke.EXAMPLE)
    assert str(structure.number) == "18-SH-0473"
    assert structure.girder_count == 4
    assert len(structure.details()) == 12


def test_the_example_has_a_section_schedule_worth_having() -> None:
    structure = importer.read(smoke.EXAMPLE)
    schedule = structure.girder("G2").schedule
    assert len(schedule) == 3
    assert schedule.section_at(48.0).inertia_in4 > schedule.section_at(6.0).inertia_in4


def test_the_example_has_details_of_more_than_one_category() -> None:
    structure = importer.read(smoke.EXAMPLE)
    categories = {detail.category_name for detail in structure.details()}
    assert len(categories) > 1


def test_the_synthetic_history_has_a_loop_per_truck() -> None:
    history = smoke._strain_history()
    assert len(history) == smoke.SAMPLE_EVENTS * 5 + 1


def test_the_synthetic_history_reaches_the_stated_peak() -> None:
    assert max(smoke._strain_history()) == pytest.approx(smoke.SAMPLE_PEAK_UE)


def test_the_synthetic_history_returns_to_zero() -> None:
    history = smoke._strain_history()
    assert history[0] == 0.0
    assert history[-1] == 0.0


def test_the_run_reports_a_line_per_step(smoke_run: Run) -> None:
    assert len(smoke_run.lines) == 8
    starts = [line.split()[0] for line in smoke_run.lines]
    assert starts == [
        "schema",
        "inventory",
        "rating",
        "posting",
        "measurement",
        "fatigue",
        "record",
        "programme",
    ]


def test_the_run_rates_every_station_on_every_girder(smoke_run: Run) -> None:
    # Four girders, nine interior stations each.
    assert "36 stations" in smoke_run.step("rating")


def test_the_run_counts_more_loops_than_trucks(smoke_run: Run) -> None:
    counted = int(smoke_run.step("measurement").split()[1])
    assert counted > smoke.SAMPLE_EVENTS


def test_the_run_leaves_most_details_unmeasured(smoke_run: Run) -> None:
    # One gauge on twelve details. The point of the line is that it says so.
    assert "1 of 12 measured" in smoke_run.step("fatigue")


def test_the_run_leaves_the_book_behind(smoke_run: Run) -> None:
    assert smoke_run.book.exists()


def test_the_book_the_run_leaves_is_consistent(smoke_run: Run) -> None:
    assert db.foreign_key_violations(smoke_run.book) == []
    assert db.integrity_check(smoke_run.book) == []


def test_the_run_ranks_the_structure_it_rated(smoke_run: Run) -> None:
    programme = smoke_run.step("programme")
    assert "18-SH-0473" in programme
    assert "months" in programme


def test_the_run_puts_a_structure_that_cannot_carry_the_load_in_the_first_band(
    smoke_run: Run,
) -> None:
    # The example rates at 0.94, which is what the restricted band is for.
    assert "restricted band" in smoke_run.step("programme")


def test_the_run_stores_the_ratings_it_ranks_on(smoke_run: Run) -> None:
    assert db.row_count(smoke_run.book, "ratings") > 0
    assert db.row_count(smoke_run.book, "programme") == 1


def test_the_run_writes_one_posting_and_one_evaluation(smoke_run: Run) -> None:
    assert db.row_count(smoke_run.book, "postings") == 1
    assert db.row_count(smoke_run.book, "evaluations") == 1


def test_the_condition_rating_the_run_uses_blocks_the_extension() -> None:
    assert smoke.CONDITION_RATING < interval.EXTENSION_CONDITION_RATING
    assert smoke.CONDITION_RATING > interval.POOR_CONDITION_RATING


def test_a_second_run_into_a_fresh_book_says_the_same_thing(smoke_run: Run, tmp_path: Path) -> None:
    # Its own book, because the point is that the run does not depend on one.
    again = smoke.run(tmp_path / "again.sqlite3")
    assert again == smoke_run.lines


def test_the_command_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert smoke.main([]) == 0
    assert "smoke: clean" in capsys.readouterr().out


def test_the_quiet_flag_prints_only_the_verdict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert smoke.main(["--quiet"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["smoke: clean"]


def test_the_command_leaves_nothing_behind(tmp_path: Path) -> None:
    before = set(tmp_path.iterdir())
    smoke.main(["--quiet"])
    assert set(tmp_path.iterdir()) == before


def test_a_failed_step_is_reported_rather_than_traced(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(book: Path) -> list[str]:
        raise AssertionError("the rating run produced nothing")

    monkeypatch.setattr(smoke, "run", boom)
    assert smoke.main([]) == 1
    assert "smoke: FAILED" in capsys.readouterr().out
