"""Remaining life, and the growth compounding that shortens it."""

from __future__ import annotations

import math

import pytest

from shearstud.errors import InputError
from shearstud.fatigue import life
from shearstud.fatigue.life import TrafficModel

pytestmark = pytest.mark.fatigue


def traffic(adtt: float = 1200.0, growth_pct: float = 2.0, lanes: int = 2) -> TrafficModel:
    return TrafficModel(
        adtt=adtt,
        lanes_available=lanes,
        growth_pct_per_yr=growth_pct,
        cycles_per_passage=1.0,
    )


@pytest.mark.parametrize("lanes,fraction", [(1, 1.00), (2, 0.85), (3, 0.80), (6, 0.80)])
def test_the_lane_fractions_are_the_published_ones(lanes: int, fraction: float) -> None:
    assert life.adtt_single_lane(1000.0, lanes) == pytest.approx(1000.0 * fraction)


def test_no_trucks_means_no_trucks_in_any_lane() -> None:
    assert life.adtt_single_lane(0.0, 3) == 0.0


def test_negative_truck_traffic_is_refused() -> None:
    with pytest.raises(InputError, match="is negative"):
        life.adtt_single_lane(-10.0, 2)


def test_a_roadway_with_no_lanes_is_refused() -> None:
    with pytest.raises(InputError, match="is not a roadway"):
        life.adtt_single_lane(1000.0, 0)


def test_a_short_simple_span_sees_two_cycles_a_truck() -> None:
    assert life.cycles_per_truck(35.0, continuous=False) == pytest.approx(2.0)


def test_a_long_simple_span_sees_one() -> None:
    assert life.cycles_per_truck(90.0, continuous=False) == pytest.approx(1.0)


def test_the_forty_foot_boundary_belongs_to_the_short_case() -> None:
    assert life.cycles_per_truck(40.0, continuous=False) == pytest.approx(2.0)
    assert life.cycles_per_truck(40.1, continuous=False) == pytest.approx(1.0)


def test_a_detail_near_a_pier_sees_half_a_cycle_more() -> None:
    away = life.cycles_per_truck(90.0, continuous=True)
    near = life.cycles_per_truck(90.0, continuous=True, near_support=True)
    assert near == pytest.approx(away + 0.5)


def test_a_simple_span_has_no_pier_to_be_near() -> None:
    with pytest.raises(InputError, match="no interior support"):
        life.cycles_per_truck(90.0, continuous=False, near_support=True)


def test_a_span_with_no_length_is_refused() -> None:
    with pytest.raises(InputError, match="is not a span"):
        life.cycles_per_truck(0.0, continuous=False)


def test_the_traffic_model_reports_the_lane_it_cares_about() -> None:
    assert traffic(adtt=1000.0, lanes=2).adtt_single_lane == pytest.approx(850.0)


def test_first_year_cycles_are_trucks_times_days_times_cycles() -> None:
    t = TrafficModel(adtt=1000.0, lanes_available=1, growth_pct_per_yr=0.0, cycles_per_passage=2.0)
    assert t.cycles_in_first_year() == pytest.approx(1000.0 * 2.0 * 365.0)


def test_growth_compounds_year_on_year() -> None:
    t = traffic(growth_pct=3.0)
    assert t.cycles_in_year(0) == pytest.approx(t.cycles_in_first_year())
    assert t.cycles_in_year(1) == pytest.approx(t.cycles_in_first_year() * 1.03)
    assert t.cycles_in_year(10) == pytest.approx(t.cycles_in_first_year() * 1.03**10)


def test_a_year_before_the_projection_is_refused() -> None:
    with pytest.raises(InputError, match="before the projection"):
        traffic().cycles_in_year(-1)


def test_flat_traffic_accumulates_linearly() -> None:
    t = traffic(growth_pct=0.0)
    assert t.cycles_through(10.0) == pytest.approx(10.0 * t.cycles_in_first_year())


def test_growing_traffic_accumulates_faster_than_linearly() -> None:
    t = traffic(growth_pct=2.0)
    assert t.cycles_through(20.0) > 20.0 * t.cycles_in_first_year()


def test_the_closed_form_matches_a_year_by_year_sum() -> None:
    t = traffic(growth_pct=2.5)
    by_hand = sum(t.cycles_in_year(y) for y in range(30))
    assert t.cycles_through(30.0) == pytest.approx(by_hand, rel=1e-9)


def test_shrinking_traffic_accumulates_slower() -> None:
    t = traffic(growth_pct=-1.5)
    assert t.cycles_through(20.0) < 20.0 * t.cycles_in_first_year()


def test_no_projection_is_no_cycles() -> None:
    assert traffic().cycles_through(0.0) == pytest.approx(0.0)


def test_a_negative_projection_is_refused() -> None:
    with pytest.raises(InputError, match="is not a projection"):
        traffic().cycles_through(-5.0)


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"adtt": -1.0}, "is negative"),
        ({"lanes_available": 0}, "is not a roadway"),
        ({"growth_pct_per_yr": -150.0}, "more than all of it"),
        ({"cycles_per_passage": 0.0}, "is not a count"),
    ],
)
def test_a_bad_traffic_model_is_refused(kwargs: dict[str, float], message: str) -> None:
    base = {
        "adtt": 1000.0,
        "lanes_available": 2,
        "growth_pct_per_yr": 2.0,
        "cycles_per_passage": 1.0,
    }
    with pytest.raises(InputError, match=message):
        TrafficModel(**{**base, **kwargs})  # type: ignore[arg-type]


def test_flat_traffic_gives_the_obvious_division() -> None:
    got = life.years_remaining(0.02, traffic(growth_pct=0.0))
    assert got == pytest.approx(50.0)


def test_growth_shortens_the_life() -> None:
    flat = life.years_remaining(0.02, traffic(growth_pct=0.0))
    growing = life.years_remaining(0.02, traffic(growth_pct=2.0))
    assert growing < flat


def test_two_percent_over_a_fifty_year_life_costs_about_a_quarter() -> None:
    flat = life.years_remaining(0.02, traffic(growth_pct=0.0))
    growing = life.years_remaining(0.02, traffic(growth_pct=2.0))
    assert 0.65 < growing / flat < 0.80


def test_shrinking_traffic_lengthens_the_life() -> None:
    flat = life.years_remaining(0.02, traffic(growth_pct=0.0))
    shrinking = life.years_remaining(0.02, traffic(growth_pct=-1.0))
    assert shrinking > flat


def test_damage_already_done_is_taken_off_the_front() -> None:
    fresh = life.years_remaining(0.02, traffic(growth_pct=0.0))
    used = life.years_remaining(0.02, traffic(growth_pct=0.0), damage_already_done=0.5)
    assert used == pytest.approx(fresh / 2.0)


def test_a_fully_used_detail_has_nothing_left() -> None:
    assert life.years_remaining(0.02, traffic(), damage_already_done=1.0) == 0.0


def test_no_damage_a_year_is_an_indefinite_life() -> None:
    assert life.years_remaining(0.0, traffic()) == math.inf


def test_the_solved_year_is_where_the_damage_reaches_one() -> None:
    t = traffic(growth_pct=2.0)
    per_year = 0.015
    years = life.years_remaining(per_year, t)
    accumulated = per_year * t.cycles_through(years) / t.cycles_in_first_year()
    assert accumulated == pytest.approx(1.0, rel=1e-6)


def test_a_negative_damage_rate_is_refused() -> None:
    with pytest.raises(InputError, match="is negative"):
        life.years_remaining(-0.01, traffic())


@pytest.mark.parametrize("done", [-0.1, 1.5])
def test_damage_already_done_outside_the_range_is_refused(done: float) -> None:
    with pytest.raises(InputError, match="outside zero to one"):
        life.years_remaining(0.01, traffic(), damage_already_done=done)


def test_the_packaged_result_carries_its_inputs() -> None:
    result = life.remaining_life("E", 0.01, traffic(growth_pct=0.0), 0.2)
    assert result.detail_category == "E"
    assert result.damage_already_done == pytest.approx(0.2)
    assert result.damage_per_first_year == pytest.approx(0.01)
    assert result.years_remaining == pytest.approx(80.0)
    assert not result.is_expired
    assert not result.is_indefinite


def test_an_expired_detail_says_so() -> None:
    result = life.remaining_life("E'", 0.05, traffic(), 1.0)
    assert result.is_expired


def test_an_undamaged_detail_says_it_is_indefinite() -> None:
    result = life.remaining_life("A", 0.0, traffic())
    assert result.is_indefinite
    assert not result.is_expired


def test_the_growth_fraction_is_the_percentage_over_a_hundred() -> None:
    assert traffic(growth_pct=2.5).growth_frac_per_yr == pytest.approx(0.025)
    assert traffic(growth_pct=0.0).growth_frac_per_yr == pytest.approx(0.0)


def test_traffic_that_is_falling_off_gives_a_negative_fraction() -> None:
    assert traffic(growth_pct=-1.5).growth_frac_per_yr == pytest.approx(-0.015)


def test_the_growth_fraction_is_what_the_compounding_uses() -> None:
    model = traffic(growth_pct=3.0)
    year_ten = model.cycles_in_first_year() * math.pow(1.0 + model.growth_frac_per_yr, 10)
    assert model.cycles_in_year(10) == pytest.approx(year_ten)
