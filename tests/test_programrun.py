"""Assembling the worklist, and refusing to guess at what is not in the book."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from shearstud.analysis import programrun as pr
from shearstud.errors import StorageError
from shearstud.fatigue.evaluation import Evaluation
from shearstud.program import priority
from shearstud.store import assessment as asm
from shearstud.store import db
from shearstud.store import programme as prog
from shearstud.store.assessment import StoredRating
from shearstud.store.programme import ProgrammeRow

pytestmark = pytest.mark.store

NUMBER = "18-SH-0473"
OTHER = "07-CR-0112"
DETAIL = "D07"
CAMPAIGN = "C-2025-04"


def add_structure(book: Path, number: str, redundancy: str = "redundant") -> None:
    db.execute(
        book,
        "INSERT INTO structures (number, name, county_code, route_class, sequence, "
        "parallel, year_built, span_lengths_ft, continuous, effective_width_rule, "
        "steel_grade, member_condition, redundancy, adtt, lanes_available, "
        "growth_pct_per_yr) VALUES (?, 'A bridge', 7, 'CR', 112, '', 1962, '[84.0]', "
        "0, 'tributary', 'A36', 'good', ?, 500, 2, 1.0)",
        (number, redundancy),
    )


def add_programme(book: Path, number: str = NUMBER, rating: int = 8, posted: bool = False) -> None:
    prog.save(
        book,
        ProgrammeRow(
            structure_number=number,
            lowest_condition_rating=rating,
            daily_traffic=3400,
            detour_mi=8.5,
            is_posted=posted,
            last_inspected=date(2025, 4, 2),
            updated_on=date(2025, 4, 9),
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


def evaluation(years: float) -> Evaluation:
    """One evaluation of the seeded book's detail, with a chosen life."""
    return Evaluation(
        detail_id=DETAIL,
        detail_category="E",
        campaign_days=30.0,
        annual_cycles=400000.0,
        effective_range_ksi=6.0,
        largest_range_ksi=9.0,
        infinite_life=False,
        damage_per_first_year=1.0 / years,
        years_remaining=years,
    )


def test_an_empty_book_gives_an_empty_worklist(book: Path) -> None:
    result = pr.build(book)
    assert result.ranked == ()
    assert result.gaps == ()
    assert result.structure_count == 0
    assert result.ranked_frac == 0.0


def test_a_structure_with_everything_is_ranked(seeded_book: Path) -> None:
    add_programme(seeded_book)
    add_rating(seeded_book)
    result = pr.build(seeded_book)
    assert [c.number for c in result.ranked] == [NUMBER]
    assert result.gaps == ()


def test_a_structure_nobody_has_inspected_is_a_gap(seeded_book: Path) -> None:
    add_rating(seeded_book)
    result = pr.build(seeded_book)
    assert result.ranked == ()
    assert result.gaps_for(pr.GAP_NO_PROGRAMME) == [NUMBER]


def test_a_structure_nobody_has_rated_is_a_gap(seeded_book: Path) -> None:
    add_programme(seeded_book)
    result = pr.build(seeded_book)
    assert result.ranked == ()
    assert result.gaps_for(pr.GAP_NEVER_RATED) == [NUMBER]


def test_the_inspection_gap_is_read_before_the_rating_one(seeded_book: Path) -> None:
    # Neither is present. It is reported once, as the first thing missing.
    result = pr.build(seeded_book)
    assert result.gaps_for(pr.GAP_NO_PROGRAMME) == [NUMBER]
    assert result.gaps_for(pr.GAP_NEVER_RATED) == []


def test_a_gap_is_never_quietly_ranked_on_a_default(seeded_book: Path) -> None:
    add_rating(seeded_book)
    result = pr.build(seeded_book)
    assert result.structure_count == 1
    assert result.ranked_frac == 0.0


def test_the_coverage_says_how_much_of_the_inventory_is_ranked(seeded_book: Path) -> None:
    add_structure(seeded_book, OTHER)
    add_programme(seeded_book)
    add_rating(seeded_book)
    result = pr.build(seeded_book)
    assert result.structure_count == 2
    assert result.ranked_frac == pytest.approx(0.5)


def test_an_unmeasured_structure_is_ranked_and_flagged(seeded_book: Path) -> None:
    add_programme(seeded_book)
    add_rating(seeded_book)
    result = pr.build(seeded_book)
    assert result.unmeasured == (NUMBER,)
    assert priority.band_of(result.ranked[0]) == priority.BAND_MONITOR


def test_an_unmeasured_structure_is_not_put_in_the_retrofit_band(seeded_book: Path) -> None:
    # Not knowing is not the same as knowing it is bad, and burying the ones
    # that are cracking under every structure nobody has gauged is how the
    # list stops being read.
    add_programme(seeded_book)
    add_rating(seeded_book)
    life, measured = pr.credited_life_years(seeded_book, NUMBER)
    assert not measured
    assert life == pr.UNMEASURED_LIFE_YEARS
    assert life >= priority.RETROFIT_YEARS


def test_a_measured_structure_uses_what_was_measured(seeded_book: Path) -> None:
    asm.save_evaluation(seeded_book, evaluation(years=3.0), CAMPAIGN, date(2025, 7, 1))
    life, measured = pr.credited_life_years(seeded_book, NUMBER)
    assert measured
    assert life == pytest.approx(3.0)


def test_a_measured_life_beyond_the_ceiling_is_capped(seeded_book: Path) -> None:
    asm.save_evaluation(seeded_book, evaluation(years=500.0), CAMPAIGN, date(2025, 7, 1))
    life, _ = pr.credited_life_years(seeded_book, NUMBER)
    assert life == pr.UNMEASURED_LIFE_YEARS


def test_a_short_life_puts_a_sound_structure_in_the_retrofit_band(seeded_book: Path) -> None:
    add_programme(seeded_book)
    add_rating(seeded_book)
    asm.save_evaluation(seeded_book, evaluation(years=2.0), CAMPAIGN, date(2025, 7, 1))
    result = pr.build(seeded_book)
    assert priority.band_of(result.ranked[0]) == priority.BAND_RETROFIT
    assert result.unmeasured == ()


def test_only_the_newest_evaluation_of_a_detail_counts(seeded_book: Path) -> None:
    # A retrofit in 2026 does not leave the 2019 number governing.
    asm.save_evaluation(seeded_book, evaluation(years=2.0), CAMPAIGN, date(2019, 7, 1))
    asm.save_evaluation(seeded_book, evaluation(years=60.0), CAMPAIGN, date(2026, 7, 1))
    life, _ = pr.credited_life_years(seeded_book, NUMBER)
    assert life == pytest.approx(60.0)


def test_a_posted_structure_lands_at_the_front(seeded_book: Path) -> None:
    add_structure(seeded_book, OTHER)
    add_programme(seeded_book, posted=True)
    add_rating(seeded_book)
    add_programme(seeded_book, number=OTHER)
    add_rating(seeded_book, number=OTHER)
    result = pr.build(seeded_book)
    assert result.ranked[0].number == NUMBER


def test_the_bands_are_counted(seeded_book: Path) -> None:
    add_programme(seeded_book)
    add_rating(seeded_book)
    numbers = pr.build(seeded_book).counts()
    assert set(numbers) == set(priority.BANDS)
    assert numbers[priority.BAND_MONITOR] == 1


def test_the_top_of_the_list_is_available_on_its_own(seeded_book: Path) -> None:
    add_programme(seeded_book)
    add_rating(seeded_book)
    assert len(pr.build(seeded_book).top(5)) == 1


def test_a_nonredundant_structure_carries_that_into_the_ranking(book: Path) -> None:
    add_structure(book, OTHER, redundancy="nonredundant")
    add_programme(book, number=OTHER)
    add_rating(book, number=OTHER)
    result = pr.build(book)
    assert result.ranked[0].state.has_nonredundant_members


def test_an_unknown_gap_reason_is_refused(book: Path) -> None:
    with pytest.raises(StorageError, match="unknown gap reason"):
        pr.Gap(NUMBER, "the inspector was ill")


def test_asking_a_worklist_for_an_unknown_gap_reason_is_refused(book: Path) -> None:
    with pytest.raises(StorageError, match="unknown gap reason"):
        pr.build(book).gaps_for("the inspector was ill")
