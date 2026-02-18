"""The inspection interval, and the asymmetry between the two ways off routine.

Any one shortener fires on its own. Every extension condition has to hold at
once. The tests are arranged around that difference because it is the thing the
office gets wrong: a structure a long way from every shortener is not thereby
eligible for the long interval.
"""

from __future__ import annotations

from datetime import date

import pytest

from shearstud.errors import InputError
from shearstud.program import interval
from shearstud.program.interval import Decision, StructureState

pytestmark = pytest.mark.program


def state(
    rating: int = 8,
    posted: bool = False,
    nonredundant: bool = False,
    life_years: float = 60.0,
) -> StructureState:
    return StructureState(
        lowest_condition_rating=rating,
        is_posted=posted,
        has_nonredundant_members=nonredundant,
        fatigue_life_years=life_years,
    )


def test_a_clean_structure_earns_the_long_interval() -> None:
    assert interval.decide(state()).months == interval.EXTENDED_MONTHS


def test_the_long_interval_says_it_was_extended() -> None:
    decision = interval.decide(state())
    assert decision.is_extended
    assert not decision.is_shortened
    assert decision.driver == interval.DRIVER_EXTENSION


def test_a_poor_component_shortens_the_interval() -> None:
    decision = interval.decide(state(rating=4))
    assert decision.months == interval.SHORT_MONTHS
    assert decision.driver == interval.DRIVER_CONDITION


def test_a_posting_shortens_the_interval() -> None:
    decision = interval.decide(state(posted=True))
    assert decision.months == interval.SHORT_MONTHS
    assert decision.driver == interval.DRIVER_POSTING


def test_a_short_fatigue_life_shortens_the_interval() -> None:
    decision = interval.decide(state(life_years=3.0))
    assert decision.months == interval.SHORT_MONTHS
    assert decision.driver == interval.DRIVER_FATIGUE


def test_one_shortener_is_enough_on_its_own() -> None:
    # Everything else about this structure is as good as it gets.
    assert interval.decide(state(rating=9, posted=True)).months == interval.SHORT_MONTHS


def test_the_reason_names_every_shortener_that_fired() -> None:
    decision = interval.decide(state(rating=3, posted=True, life_years=1.0))
    assert interval.DRIVER_CONDITION in decision.reason
    assert interval.DRIVER_POSTING in decision.reason
    assert interval.DRIVER_FATIGUE in decision.reason


def test_a_non_redundant_structure_stays_on_routine() -> None:
    # Non redundancy blocks the extension. It is not a shortener, and the
    # difference between those two is a year of inspection budget.
    decision = interval.decide(state(nonredundant=True))
    assert decision.months == interval.ROUTINE_MONTHS
    assert decision.driver == interval.DRIVER_REDUNDANCY


def test_a_middling_condition_rating_blocks_without_shortening() -> None:
    decision = interval.decide(state(rating=6))
    assert decision.months == interval.ROUTINE_MONTHS
    assert decision.driver == interval.DRIVER_CONDITION


def test_the_rating_that_just_qualifies_gets_the_extension() -> None:
    assert interval.decide(state(rating=7)).months == interval.EXTENDED_MONTHS
    assert interval.decide(state(rating=6)).months == interval.ROUTINE_MONTHS


def test_a_life_between_the_two_thresholds_blocks_without_shortening() -> None:
    decision = interval.decide(state(life_years=12.0))
    assert decision.months == interval.ROUTINE_MONTHS
    assert decision.driver == interval.DRIVER_FATIGUE


def test_the_life_that_just_qualifies_gets_the_extension() -> None:
    assert interval.decide(state(life_years=20.0)).months == interval.EXTENDED_MONTHS
    assert interval.decide(state(life_years=19.9)).months == interval.ROUTINE_MONTHS


def test_the_life_that_just_shortens() -> None:
    assert interval.decide(state(life_years=5.0)).months == interval.ROUTINE_MONTHS
    assert interval.decide(state(life_years=4.9)).months == interval.SHORT_MONTHS


def test_a_structure_far_from_every_shortener_can_still_be_ineligible() -> None:
    # Rating 6 is nowhere near poor and twelve years is nowhere near five, and
    # neither of those buys the extension.
    clear_of_shorteners = state(rating=6, life_years=12.0)
    assert interval.shorteners(clear_of_shorteners) == []
    assert interval.decide(clear_of_shorteners).months == interval.ROUTINE_MONTHS


def test_the_blockers_are_listed_one_by_one() -> None:
    blocked = interval.extension_blockers(state(rating=5, nonredundant=True, life_years=8.0))
    assert blocked == [
        interval.DRIVER_CONDITION,
        interval.DRIVER_REDUNDANCY,
        interval.DRIVER_FATIGUE,
    ]


def test_a_clean_structure_has_no_blockers() -> None:
    assert interval.extension_blockers(state()) == []


def test_the_routine_reason_names_what_blocked_the_extension() -> None:
    assert "extension blocked by" in interval.decide(state(nonredundant=True)).reason


@pytest.mark.parametrize("rating", [0, 1, 4])
def test_every_poor_rating_shortens(rating: int) -> None:
    assert interval.decide(state(rating=rating)).months == interval.SHORT_MONTHS


def test_only_the_number_is_available_for_a_caller_that_wants_it() -> None:
    assert interval.months_for(state()) == interval.EXTENDED_MONTHS
    assert interval.months_for(state(posted=True)) == interval.SHORT_MONTHS


def test_a_rating_off_the_scale_is_refused() -> None:
    with pytest.raises(InputError, match="outside 0 to 9"):
        state(rating=10)
    with pytest.raises(InputError, match="outside 0 to 9"):
        state(rating=-1)


def test_a_negative_fatigue_life_is_refused() -> None:
    with pytest.raises(InputError, match="is not a life"):
        state(life_years=-1.0)


def test_an_interval_nobody_writes_down_is_refused() -> None:
    with pytest.raises(InputError, match="not an interval"):
        Decision(months=30, driver=interval.DRIVER_ROUTINE, reason="split the difference")


def test_every_allowed_interval_can_be_built() -> None:
    for months in interval.ALLOWED_MONTHS:
        assert Decision(months, interval.DRIVER_ROUTINE, "because").months == months


def test_the_due_date_is_the_interval_after_the_last_one() -> None:
    decision = interval.decide(state(nonredundant=True))
    due = decision.next_due(date(2025, 3, 10))
    assert due.year == 2027
    assert due.month == 3


def test_the_long_interval_falls_two_years_later_than_routine() -> None:
    routine = interval.decide(state(nonredundant=True)).next_due(date(2025, 3, 10))
    extended = interval.decide(state()).next_due(date(2025, 3, 10))
    assert (extended - routine).days == pytest.approx(730, abs=2)


def test_a_structure_inside_its_interval_is_not_overdue() -> None:
    decision = interval.decide(state())
    assert not decision.is_overdue(date(2025, 3, 10), date(2027, 1, 1))


def test_a_structure_past_its_interval_is_overdue() -> None:
    decision = interval.decide(state())
    assert decision.is_overdue(date(2025, 3, 10), date(2030, 1, 1))


def test_the_day_the_interval_lands_on_is_not_yet_overdue() -> None:
    decision = interval.decide(state())
    due = decision.next_due(date(2025, 3, 10))
    assert not decision.is_overdue(date(2025, 3, 10), due)


def test_the_soonest_of_several_inspections_governs() -> None:
    routine = interval.decide(state(nonredundant=True))
    extended = interval.decide(state())
    last = date(2025, 3, 10)
    assert interval.soonest([extended, routine], last) == routine.next_due(last)


def test_comparing_no_inspections_is_refused() -> None:
    with pytest.raises(InputError, match="no decisions"):
        interval.soonest([], date(2025, 3, 10))


def test_poor_condition_is_read_off_the_rating() -> None:
    assert state(rating=4).is_poor
    assert not state(rating=5).is_poor


def test_a_pressing_fatigue_life_is_the_one_below_the_shortener() -> None:
    assert state(life_years=4.9).fatigue_is_pressing
    assert not state(life_years=5.0).fatigue_is_pressing


def test_the_two_fatigue_questions_are_not_opposites() -> None:
    # Between the thresholds both come back false, which is the gap the routine
    # interval lives in.
    middle = state(life_years=12.0)
    assert not middle.fatigue_is_pressing
    assert not middle.fatigue_allows_extension


def test_a_long_life_allows_the_extension() -> None:
    assert state(life_years=20.0).fatigue_allows_extension
    assert not state(life_years=19.9).fatigue_allows_extension
