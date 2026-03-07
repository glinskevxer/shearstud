"""The one table in the book that is overwritten rather than appended to."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from shearstud.errors import StorageError
from shearstud.program import priority
from shearstud.store import db
from shearstud.store import programme as prog
from shearstud.store.programme import ProgrammeRow

pytestmark = pytest.mark.store

NUMBER = "18-SH-0473"


def row(
    number: str = NUMBER,
    rating: int = 7,
    traffic: int = 3400,
    detour_mi: float = 8.5,
    posted: bool = False,
    inspected: date = date(2025, 4, 2),
    updated: date = date(2025, 4, 9),
) -> ProgrammeRow:
    return ProgrammeRow(
        structure_number=number,
        lowest_condition_rating=rating,
        daily_traffic=traffic,
        detour_mi=detour_mi,
        is_posted=posted,
        last_inspected=inspected,
        updated_on=updated,
    )


def test_a_row_round_trips(seeded_book: Path) -> None:
    prog.save(seeded_book, row())
    loaded = prog.load(seeded_book, NUMBER)
    assert loaded.lowest_condition_rating == 7
    assert loaded.daily_traffic == 3400
    assert loaded.detour_mi == pytest.approx(8.5)
    assert loaded.last_inspected == date(2025, 4, 2)


def test_the_posted_flag_survives_the_round_trip(seeded_book: Path) -> None:
    prog.save(seeded_book, row(posted=True))
    assert prog.load(seeded_book, NUMBER).is_posted is True


def test_saving_again_replaces_rather_than_appends(seeded_book: Path) -> None:
    prog.save(seeded_book, row(rating=7))
    prog.save(seeded_book, row(rating=5, updated=date(2026, 4, 9)))
    assert db.row_count(seeded_book, "programme") == 1
    assert prog.load(seeded_book, NUMBER).lowest_condition_rating == 5


def test_a_structure_nobody_has_inspected_has_no_row(seeded_book: Path) -> None:
    with pytest.raises(StorageError, match="no programme row"):
        prog.load(seeded_book, NUMBER)


def test_finding_a_missing_row_gives_nothing_rather_than_raising(seeded_book: Path) -> None:
    assert prog.find(seeded_book, NUMBER) is None
    prog.save(seeded_book, row())
    found = prog.find(seeded_book, NUMBER)
    assert found is not None
    assert found.structure_number == NUMBER


def test_the_uninspected_list_names_the_gap(seeded_book: Path) -> None:
    assert prog.uninspected(seeded_book) == [NUMBER]
    prog.save(seeded_book, row())
    assert prog.uninspected(seeded_book) == []


def test_everything_comes_back_by_number(seeded_book: Path) -> None:
    prog.save(seeded_book, row())
    assert [r.structure_number for r in prog.load_all(seeded_book)] == [NUMBER]


def test_an_empty_book_has_no_programme_rows(book: Path) -> None:
    assert prog.load_all(book) == []


def test_a_row_goes_away_when_it_is_deleted(seeded_book: Path) -> None:
    prog.save(seeded_book, row())
    prog.delete(seeded_book, NUMBER)
    assert prog.find(seeded_book, NUMBER) is None


def test_deleting_a_row_that_is_not_there_is_quiet(seeded_book: Path) -> None:
    prog.delete(seeded_book, NUMBER)
    assert db.row_count(seeded_book, "programme") == 0


def test_the_row_goes_when_the_structure_does(seeded_book: Path) -> None:
    prog.save(seeded_book, row())
    db.execute(seeded_book, "DELETE FROM structures WHERE number = ?", (NUMBER,))
    assert db.row_count(seeded_book, "programme") == 0


def test_a_row_for_a_structure_nobody_has_is_refused(seeded_book: Path) -> None:
    with pytest.raises(Exception, match="FOREIGN KEY"):
        prog.save(seeded_book, row(number="99-XX-9999"))


def test_the_inspection_date_filter_finds_the_old_ones(seeded_book: Path) -> None:
    prog.save(seeded_book, row(inspected=date(2019, 6, 1), updated=date(2019, 6, 5)))
    assert len(prog.due_before(seeded_book, date(2024, 1, 1))) == 1
    assert prog.due_before(seeded_book, date(2019, 1, 1)) == []


def test_the_date_filter_puts_the_oldest_first(seeded_book: Path, book: Path) -> None:
    prog.save(seeded_book, row(inspected=date(2021, 6, 1), updated=date(2021, 6, 5)))
    found = prog.due_before(seeded_book, date(2026, 1, 1))
    assert [r.last_inspected for r in found] == sorted(r.last_inspected for r in found)


def test_a_row_with_no_structure_number_is_refused() -> None:
    with pytest.raises(StorageError, match="needs a structure number"):
        row(number="   ")


def test_a_condition_rating_off_the_scale_is_refused() -> None:
    with pytest.raises(StorageError, match="outside 0 to 9"):
        row(rating=10)


def test_negative_traffic_is_refused() -> None:
    with pytest.raises(StorageError, match="traffic -5 is negative"):
        row(traffic=-5)


def test_a_negative_detour_is_refused() -> None:
    with pytest.raises(StorageError, match="is not a detour"):
        row(detour_mi=-1.0)


def test_a_row_written_before_the_inspection_it_describes_is_refused() -> None:
    # An inspection date in the future of the row that records it is a typed
    # year, and it is worth catching at the point of entry.
    with pytest.raises(StorageError, match="before the"):
        row(inspected=date(2026, 4, 2), updated=date(2025, 4, 9))


def test_a_row_written_the_day_of_the_inspection_is_allowed() -> None:
    assert row(inspected=date(2025, 4, 2), updated=date(2025, 4, 2)).updated_on == date(2025, 4, 2)


def test_a_row_becomes_a_state_the_interval_rule_can_read() -> None:
    state = row(rating=5, posted=True).state(fatigue_life_years=40.0)
    assert state.lowest_condition_rating == 5
    assert state.is_posted
    assert state.fatigue_life_years == pytest.approx(40.0)
    assert not state.has_nonredundant_members


def test_the_redundancy_is_asked_for_rather_than_stored() -> None:
    # It belongs to the structure's geometry, not to the inspection programme.
    assert row().state(40.0, nonredundant=True).has_nonredundant_members


def test_a_row_becomes_a_candidate_the_ranking_can_order() -> None:
    candidate = row(traffic=3400, detour_mi=8.5).candidate(
        rating_factor=1.35, fatigue_life_years=40.0
    )
    assert candidate.number == NUMBER
    assert candidate.user_cost_index == pytest.approx(3400 * 8.5)
    assert priority.band_of(candidate) == priority.BAND_MONITOR


def test_a_posted_row_becomes_a_restricted_candidate() -> None:
    candidate = row(posted=True).candidate(rating_factor=1.35, fatigue_life_years=40.0)
    assert priority.band_of(candidate) == priority.BAND_RESTRICTED


def test_the_fatigue_life_is_not_kept_in_this_table() -> None:
    # It comes out of an evaluation run and changes with every campaign, so a
    # copy here would be a second answer to the same question.
    columns = set(prog.PROGRAMME_COLUMNS.replace(" ", "").split(","))
    assert not any("fatigue" in column for column in columns)
    assert not any("life" in column for column in columns)
