"""Banding, and the cross band comparison the module refuses to make.

The test that matters most here is the one where a sound structure carrying
enormous traffic still comes below a posted one carrying almost none. Every
weighted score gets that wrong eventually, and it is the reason there is no
score.
"""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.program import priority
from shearstud.program.interval import StructureState
from shearstud.program.priority import Candidate

pytestmark = pytest.mark.program


def candidate(
    number: str = "18-SH-0473",
    rating_factor: float = 1.4,
    rating: int = 8,
    posted: bool = False,
    life_years: float = 60.0,
    traffic: int = 4000,
    detour_mi: float = 6.0,
) -> Candidate:
    return Candidate(
        number=number,
        state=StructureState(
            lowest_condition_rating=rating,
            is_posted=posted,
            has_nonredundant_members=False,
            fatigue_life_years=life_years,
        ),
        rating_factor=rating_factor,
        daily_traffic=traffic,
        detour_mi=detour_mi,
    )


def test_a_sound_structure_is_only_monitored() -> None:
    assert priority.band_of(candidate()) == priority.BAND_MONITOR


def test_a_rating_factor_below_one_restricts() -> None:
    assert priority.band_of(candidate(rating_factor=0.86)) == priority.BAND_RESTRICTED


def test_a_rating_factor_of_exactly_one_does_not() -> None:
    assert priority.band_of(candidate(rating_factor=1.0)) == priority.BAND_MONITOR


def test_a_posted_structure_is_restricted_whatever_its_rating_says() -> None:
    # Posted at a lower load, so it rates above one against that load and is
    # still a restricted structure.
    assert priority.band_of(candidate(rating_factor=1.3, posted=True)) == priority.BAND_RESTRICTED


def test_a_short_fatigue_life_puts_a_sound_structure_in_retrofit() -> None:
    assert priority.band_of(candidate(life_years=3.0)) == priority.BAND_RETROFIT


def test_a_worn_structure_with_life_left_is_for_preservation() -> None:
    assert priority.band_of(candidate(rating=6)) == priority.BAND_PRESERVE


def test_the_rating_that_just_escapes_preservation() -> None:
    assert priority.band_of(candidate(rating=7)) == priority.BAND_MONITOR
    assert priority.band_of(candidate(rating=6)) == priority.BAND_PRESERVE


def test_the_first_band_that_fits_wins() -> None:
    # Everything is wrong with this one. It is reported once, in the band that
    # decides what happens to it.
    everything = candidate(rating_factor=0.7, rating=3, life_years=1.0)
    assert priority.band_of(everything) == priority.BAND_RESTRICTED


def test_a_restricted_structure_outranks_a_sound_one_carrying_far_more() -> None:
    posted_backroad = candidate("07-CR-0112", posted=True, traffic=90, detour_mi=1.0)
    sound_arterial = candidate("21-US-0044", traffic=48000, detour_mi=30.0)
    order = priority.worklist([sound_arterial, posted_backroad])
    assert [c.number for c in order] == ["07-CR-0112", "21-US-0044"]


def test_traffic_orders_the_restricted_band_and_only_that_band() -> None:
    quiet = candidate("07-CR-0112", rating_factor=0.7, traffic=90, detour_mi=1.0)
    busy = candidate("21-US-0044", rating_factor=0.7, traffic=48000, detour_mi=30.0)
    order = priority.in_band([quiet, busy], priority.BAND_RESTRICTED)
    assert [c.number for c in order] == ["21-US-0044", "07-CR-0112"]


def test_the_retrofit_band_is_ordered_by_life_not_by_traffic() -> None:
    soon = candidate("07-CR-0112", life_years=1.0, traffic=90, detour_mi=1.0)
    later = candidate("21-US-0044", life_years=4.0, traffic=48000, detour_mi=30.0)
    order = priority.in_band([later, soon], priority.BAND_RETROFIT)
    assert [c.number for c in order] == ["07-CR-0112", "21-US-0044"]


def test_the_preservation_band_is_ordered_by_condition() -> None:
    worse = candidate("07-CR-0112", rating=4, traffic=90)
    better = candidate("21-US-0044", rating=6, traffic=48000)
    order = priority.in_band([better, worse], priority.BAND_PRESERVE)
    assert [c.number for c in order] == ["07-CR-0112", "21-US-0044"]


def test_a_tie_inside_a_band_is_broken_by_the_structure_number() -> None:
    first = candidate("07-CR-0112", life_years=2.0)
    second = candidate("21-US-0044", life_years=2.0)
    order = priority.in_band([second, first], priority.BAND_RETROFIT)
    assert [c.number for c in order] == ["07-CR-0112", "21-US-0044"]


def test_the_worklist_runs_the_bands_in_order() -> None:
    entries = [
        candidate("A", rating=8),
        candidate("B", rating=5),
        candidate("C", life_years=2.0),
        candidate("D", rating_factor=0.5),
    ]
    assert [c.number for c in priority.worklist(entries)] == ["D", "C", "B", "A"]


def test_the_worklist_keeps_everything_it_was_given() -> None:
    entries = [candidate(str(n), rating_factor=0.5 + n * 0.4) for n in range(6)]
    assert len(priority.worklist(entries)) == len(entries)


def test_an_empty_inventory_has_an_empty_worklist() -> None:
    assert priority.worklist([]) == []


def test_the_counts_name_every_band_even_the_empty_ones() -> None:
    numbers = priority.counts([candidate()])
    assert set(numbers) == set(priority.BANDS)
    assert numbers[priority.BAND_MONITOR] == 1
    assert numbers[priority.BAND_RESTRICTED] == 0


def test_the_counts_add_up_to_the_inventory() -> None:
    entries = [
        candidate("A"),
        candidate("B", rating=5),
        candidate("C", life_years=2.0),
        candidate("D", rating_factor=0.5),
    ]
    assert sum(priority.counts(entries).values()) == len(entries)


def test_the_top_of_the_list_is_the_front_of_the_worklist() -> None:
    entries = [candidate("A"), candidate("B", rating_factor=0.5), candidate("C", rating=5)]
    assert [c.number for c in priority.top(entries, 2)] == ["B", "C"]


def test_asking_for_none_of_the_list_is_refused() -> None:
    with pytest.raises(InputError, match="is not a list"):
        priority.top([candidate()], 0)


def test_asking_for_more_than_there_is_gives_what_there_is() -> None:
    assert len(priority.top([candidate()], 50)) == 1


def test_an_unknown_band_is_refused() -> None:
    with pytest.raises(InputError, match="unknown band"):
        priority.in_band([candidate()], "urgent")


def test_the_user_cost_index_is_traffic_times_detour() -> None:
    assert candidate(traffic=4000, detour_mi=6.0).user_cost_index == pytest.approx(24000.0)


def test_a_structure_with_no_detour_costs_the_public_nothing_to_close() -> None:
    assert candidate(detour_mi=0.0).user_cost_index == 0.0


def test_the_reason_names_the_rating_factor_for_a_restricted_structure() -> None:
    assert "0.86" in priority.reason_for(candidate(rating_factor=0.86))


def test_the_reason_for_a_posted_structure_says_so() -> None:
    assert priority.reason_for(candidate(posted=True)) == "already posted"


def test_the_reason_names_the_years_for_a_retrofit() -> None:
    assert "3.0 years" in priority.reason_for(candidate(life_years=3.0))


def test_the_reason_names_the_rating_for_preservation() -> None:
    assert "condition rating 5" in priority.reason_for(candidate(rating=5))


def test_the_reason_for_a_monitored_structure_says_nothing_is_wrong() -> None:
    assert "life and condition to spare" in priority.reason_for(candidate())


def test_every_band_says_what_it_measures() -> None:
    assert set(priority.BAND_MEASURE) == set(priority.BANDS)
    for measure in priority.BAND_MEASURE.values():
        assert measure


def test_a_candidate_with_no_number_is_refused() -> None:
    with pytest.raises(InputError, match="needs a structure number"):
        candidate(number="  ")


def test_a_negative_rating_factor_is_refused() -> None:
    with pytest.raises(InputError, match="rating factor -0.1 is negative"):
        candidate(rating_factor=-0.1)


def test_negative_traffic_is_refused() -> None:
    with pytest.raises(InputError, match="traffic -1 is negative"):
        candidate(traffic=-1)


def test_a_negative_detour_is_refused() -> None:
    with pytest.raises(InputError, match="is not a detour"):
        candidate(detour_mi=-3.0)


def test_a_structure_is_restricted_when_it_cannot_carry_what_it_was_rated_for() -> None:
    assert candidate(rating_factor=0.99).is_restricted
    assert not candidate(rating_factor=1.0).is_restricted


def test_a_posted_structure_need_not_be_restricted_by_its_rating() -> None:
    # Posting is a separate route into the band, and this is the case that
    # shows the two are not the same question.
    posted = candidate(rating_factor=1.3, posted=True)
    assert not posted.is_restricted
    assert priority.band_of(posted) == priority.BAND_RESTRICTED
