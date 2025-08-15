"""The rating equation, worked against numbers that can be checked by hand."""

from __future__ import annotations

import math

import pytest

from shearstud.errors import InputError, NotRatedError
from shearstud.rating import factors as fac
from shearstud.rating import rate as rt
from shearstud.rating.rate import DeadLoad, RatingFactor

pytestmark = pytest.mark.rating


def good_factors() -> fac.ResistanceFactors:
    return fac.resistance_factors("good", "redundant")


def dead(component: float = 900.0, surface: float = 200.0) -> DeadLoad:
    return DeadLoad(component=component, wearing_surface=surface)


def rating(
    capacity: float = 6000.0,
    live: float = 1400.0,
    gamma_live: float = 1.75,
    gross_kip: float = 72.0,
    factors: fac.ResistanceFactors | None = None,
) -> RatingFactor:
    return rt.rate(
        label="G3 midspan Strength I inventory",
        vehicle="HL93-TRUCK",
        nominal_capacity=capacity,
        factors=factors or good_factors(),
        dead=dead(),
        gamma_dc=1.25,
        gamma_dw=1.50,
        live_effect=live,
        gamma_live=gamma_live,
        gross_weight_kip=gross_kip,
    )


def test_the_dead_load_splits_into_two_parts() -> None:
    d = dead()
    assert d.total == pytest.approx(1100.0)
    assert d.factored(1.25, 1.50) == pytest.approx(1.25 * 900.0 + 1.50 * 200.0)


def test_each_dead_load_part_carries_its_own_factor() -> None:
    d = dead(component=1000.0, surface=1000.0)
    assert d.factored(1.25, 1.50) == pytest.approx(2750.0)
    assert d.factored(1.25, 1.25) < d.factored(1.25, 1.50)


def test_the_rating_factor_is_the_equation() -> None:
    r = rating()
    expected = (6000.0 - (1.25 * 900.0 + 1.50 * 200.0)) / (1.75 * 1400.0)
    assert r.value == pytest.approx(expected)


def test_the_capacity_carries_the_resistance_factors() -> None:
    poor = fac.resistance_factors("poor", "non_redundant")
    r = rating(factors=poor)
    assert r.capacity == pytest.approx(0.85 * 6000.0)


def test_a_poor_member_rates_lower() -> None:
    good = rating().value
    poor = rating(factors=fac.resistance_factors("poor", "non_redundant")).value
    assert poor < good


def test_the_available_capacity_is_what_the_dead_load_left() -> None:
    r = rating()
    assert r.available == pytest.approx(r.capacity - r.factored_dead)


def test_the_dead_load_share_is_reported() -> None:
    r = rating()
    assert r.dead_load_share == pytest.approx(r.factored_dead / r.capacity)
    assert 0.0 < r.dead_load_share < 1.0


def test_a_rating_above_one_is_adequate() -> None:
    assert rating(capacity=9000.0).is_adequate


def test_a_rating_below_one_is_not() -> None:
    assert not rating(capacity=3000.0).is_adequate


def test_a_rating_of_exactly_one_is_adequate() -> None:
    # Choose the capacity that makes the numerator equal the denominator.
    live = 1400.0
    gamma_live = 1.75
    dead_factored = 1.25 * 900.0 + 1.50 * 200.0
    capacity = dead_factored + gamma_live * live
    r = rating(capacity=capacity, live=live, gamma_live=gamma_live)
    assert r.value == pytest.approx(1.0)
    assert r.is_adequate


def test_a_higher_live_load_factor_lowers_the_rating() -> None:
    inventory = rating(gamma_live=1.75).value
    operating = rating(gamma_live=1.35).value
    assert operating > inventory


def test_a_heavier_live_load_effect_lowers_the_rating() -> None:
    assert rating(live=2000.0).value < rating(live=1400.0).value


def test_the_sign_of_the_live_load_effect_does_not_matter() -> None:
    assert rating(live=-1400.0).value == pytest.approx(rating(live=1400.0).value)


def test_a_section_no_vehicle_can_load_rates_infinite() -> None:
    r = rating(live=0.0)
    assert math.isinf(r.value)
    assert r.is_adequate
    assert math.isinf(r.tonnage_kip())


def test_the_tonnage_is_the_factor_times_the_vehicle_weight() -> None:
    r = rating(gross_kip=72.0)
    assert r.tonnage_kip() == pytest.approx(r.value * 72.0)


def test_the_tonnage_in_tons_is_half_the_kips() -> None:
    r = rating()
    assert r.tonnage_tons() == pytest.approx(r.tonnage_kip() / 2.0)


def test_the_weight_comes_off_the_result_not_from_a_caller() -> None:
    light = rating(gross_kip=50.0)
    heavy = rating(gross_kip=80.0)
    assert light.value == pytest.approx(heavy.value)
    assert heavy.tonnage_kip() > light.tonnage_kip()


def test_a_dead_load_heavier_than_the_capacity_rates_negative() -> None:
    r = rt.rate(
        label="overloaded",
        vehicle="TYPE3",
        nominal_capacity=800.0,
        factors=good_factors(),
        dead=dead(),
        gamma_dc=1.25,
        gamma_dw=1.50,
        live_effect=500.0,
        gamma_live=1.65,
        gross_weight_kip=50.0,
    )
    assert r.value < 0.0
    assert not r.is_adequate


def test_a_capacity_of_zero_is_refused() -> None:
    with pytest.raises(InputError, match="is not a capacity"):
        rating(capacity=0.0)


def test_a_live_load_factor_of_zero_is_refused() -> None:
    with pytest.raises(InputError, match="is not a factor"):
        rating(gamma_live=0.0)


def test_a_dead_load_factor_of_zero_is_refused() -> None:
    with pytest.raises(InputError, match="must be positive"):
        rt.rate(
            label="bad",
            vehicle="TYPE3",
            nominal_capacity=6000.0,
            factors=good_factors(),
            dead=dead(),
            gamma_dc=0.0,
            gamma_dw=1.5,
            live_effect=1400.0,
            gamma_live=1.65,
            gross_weight_kip=50.0,
        )


def test_a_rating_needs_a_label() -> None:
    with pytest.raises(InputError, match="needs a label"):
        RatingFactor(
            label=" ",
            vehicle="TYPE3",
            capacity=1.0,
            factored_dead=0.0,
            factored_live=1.0,
            gross_weight_kip=50.0,
        )


def test_a_vehicle_with_no_weight_is_refused() -> None:
    with pytest.raises(InputError, match="is not a weight"):
        rating(gross_kip=0.0)


def test_the_governing_rating_is_the_lowest() -> None:
    ratings = [
        rating(capacity=9000.0),
        rating(capacity=4000.0),
        rating(capacity=7000.0),
    ]
    assert rt.governing(ratings).capacity == pytest.approx(4000.0)


def test_the_controlling_vehicle_comes_off_the_governing_rating() -> None:
    a = rt.rate(
        label="a",
        vehicle="TYPE3",
        nominal_capacity=9000.0,
        factors=good_factors(),
        dead=dead(),
        gamma_dc=1.25,
        gamma_dw=1.50,
        live_effect=1400.0,
        gamma_live=1.65,
        gross_weight_kip=50.0,
    )
    b = rt.rate(
        label="b",
        vehicle="TYPE3-3",
        nominal_capacity=4000.0,
        factors=good_factors(),
        dead=dead(),
        gamma_dc=1.25,
        gamma_dw=1.50,
        live_effect=1400.0,
        gamma_live=1.65,
        gross_weight_kip=80.0,
    )
    assert rt.controlling_vehicle([a, b]) == "TYPE3-3"


def test_choosing_between_no_ratings_is_a_state_error() -> None:
    with pytest.raises(NotRatedError, match="no ratings to choose"):
        rt.governing([])


def test_a_set_of_adequate_ratings_passes() -> None:
    assert rt.all_adequate([rating(capacity=9000.0), rating(capacity=8000.0)])


def test_one_inadequate_rating_fails_the_set() -> None:
    assert not rt.all_adequate([rating(capacity=9000.0), rating(capacity=3000.0)])


def test_checking_an_empty_set_is_a_state_error() -> None:
    with pytest.raises(NotRatedError, match="no ratings to check"):
        rt.all_adequate([])
