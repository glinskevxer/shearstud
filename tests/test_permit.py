"""Permit ratings: the conditions are inputs to the factor, not decoration."""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.rating import permit as pm
from shearstud.rating.permit import PermitConditions

pytestmark = pytest.mark.rating


def conditions(
    kind: str = pm.SINGLE_TRIP, control: str = pm.MIXED, adtt: float = 800.0
) -> PermitConditions:
    return PermitConditions(kind=kind, control=control, adtt=adtt)


def test_a_routine_permit_carries_the_heaviest_factor() -> None:
    routine = conditions(kind=pm.ROUTINE, control=pm.MIXED).live_factor
    single = conditions(kind=pm.SINGLE_TRIP, control=pm.MIXED).live_factor
    assert routine > single


def test_escorting_buys_the_lowest_factor() -> None:
    mixed = conditions(control=pm.MIXED).live_factor
    escorted = conditions(control=pm.ESCORTED).live_factor
    assert escorted < mixed


def test_the_factors_are_the_published_ones() -> None:
    assert conditions(pm.ROUTINE, pm.MIXED).live_factor == pytest.approx(1.40)
    assert conditions(pm.SINGLE_TRIP, pm.MIXED).live_factor == pytest.approx(1.20)
    assert conditions(pm.SINGLE_TRIP, pm.ESCORTED).live_factor == pytest.approx(1.10)


def test_a_busy_structure_loses_the_routine_permit_discount() -> None:
    quiet = conditions(kind=pm.ROUTINE, adtt=1000.0).live_factor
    busy = conditions(kind=pm.ROUTINE, adtt=9000.0).live_factor
    assert busy > quiet
    assert busy == pytest.approx(1.50)


def test_the_traffic_floor_does_not_touch_a_single_trip_permit() -> None:
    quiet = conditions(kind=pm.SINGLE_TRIP, adtt=100.0).live_factor
    busy = conditions(kind=pm.SINGLE_TRIP, adtt=9000.0).live_factor
    assert quiet == pytest.approx(busy)


def test_the_traffic_floor_bites_at_the_stated_volume() -> None:
    below = conditions(kind=pm.ROUTINE, adtt=4999.0).live_factor
    at = conditions(kind=pm.ROUTINE, adtt=5000.0).live_factor
    assert at > below


def test_an_escorted_crossing_gets_no_dynamic_allowance() -> None:
    assert conditions(control=pm.ESCORTED).allowance_frac == pytest.approx(0.0)


def test_a_mixed_crossing_takes_the_ordinary_allowance() -> None:
    assert conditions(control=pm.MIXED).allowance_frac == pytest.approx(0.33)


def test_an_escorted_crossing_loads_one_lane() -> None:
    assert conditions(control=pm.ESCORTED).lanes_loaded == 1


def test_a_mixed_crossing_has_to_allow_for_a_neighbour() -> None:
    assert conditions(control=pm.MIXED).lanes_loaded == 2


def test_an_escorted_crossing_is_controlled() -> None:
    assert conditions(control=pm.ESCORTED).is_controlled
    assert not conditions(control=pm.MIXED).is_controlled


def test_a_routine_permit_cannot_be_escorted() -> None:
    with pytest.raises(InputError, match="crosses unannounced"):
        conditions(kind=pm.ROUTINE, control=pm.ESCORTED)


def test_an_unknown_permit_kind_is_refused() -> None:
    with pytest.raises(InputError, match="unknown permit kind"):
        conditions(kind="overweight")


def test_an_unknown_crossing_control_is_refused() -> None:
    with pytest.raises(InputError, match="unknown crossing control"):
        conditions(control="police")


def test_negative_truck_traffic_is_refused() -> None:
    with pytest.raises(InputError, match="is negative"):
        conditions(adtt=-5.0)


def test_the_shortcut_gives_the_same_factor_as_the_record() -> None:
    assert pm.live_factor(pm.SINGLE_TRIP, pm.MIXED, 800.0) == pytest.approx(
        conditions().live_factor
    )


def test_the_shortcut_still_refuses_a_bad_combination() -> None:
    with pytest.raises(InputError, match="crosses unannounced"):
        pm.live_factor(pm.ROUTINE, pm.ESCORTED, 800.0)


def test_a_rating_of_one_is_issuable() -> None:
    assert pm.is_issuable(1.0)
    assert pm.is_issuable(1.35)
    assert not pm.is_issuable(0.99)


def test_the_margin_is_what_is_left_over() -> None:
    assert pm.margin(1.35) == pytest.approx(0.35)
    assert pm.margin(0.8) == pytest.approx(-0.2)


def test_a_vehicle_that_rates_mixed_needs_no_escort() -> None:
    got = pm.tightest_control_needed({pm.MIXED: 1.15, pm.ESCORTED: 1.30})
    assert got == pm.MIXED


def test_a_vehicle_that_only_rates_escorted_gets_an_escort() -> None:
    got = pm.tightest_control_needed({pm.MIXED: 0.92, pm.ESCORTED: 1.06})
    assert got == pm.ESCORTED


def test_a_vehicle_that_rates_nowhere_is_refused() -> None:
    with pytest.raises(InputError, match="does not rate under any control"):
        pm.tightest_control_needed({pm.MIXED: 0.6, pm.ESCORTED: 0.8})


def test_a_routine_permit_has_only_one_control_to_try() -> None:
    got = pm.tightest_control_needed({pm.MIXED: 1.05}, kind=pm.ROUTINE)
    assert got == pm.MIXED


def test_a_routine_permit_that_fails_mixed_cannot_be_escorted_into_shape() -> None:
    with pytest.raises(InputError, match="does not rate under any control"):
        pm.tightest_control_needed({pm.MIXED: 0.9, pm.ESCORTED: 1.4}, kind=pm.ROUTINE)


def test_a_missing_control_rating_is_refused() -> None:
    with pytest.raises(InputError, match="no rating supplied for a escorted crossing"):
        pm.tightest_control_needed({pm.MIXED: 0.9})


def test_an_unknown_kind_is_refused_by_the_control_search() -> None:
    with pytest.raises(InputError, match="unknown permit kind"):
        pm.tightest_control_needed({pm.MIXED: 1.2}, kind="annual")
