"""Rating factors, including the interpolation and the floor."""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.rating import factors as fac
from shearstud.rating.factors import ResistanceFactors

pytestmark = pytest.mark.rating


def test_strength_dead_load_factors_are_the_published_ones() -> None:
    dc, dw = fac.dead_load_factors(fac.STRENGTH_I)
    assert dc == pytest.approx(1.25)
    assert dw == pytest.approx(1.50)


def test_measuring_the_wearing_surface_lowers_its_factor() -> None:
    _, plans = fac.dead_load_factors(fac.STRENGTH_I)
    _, measured = fac.dead_load_factors(fac.STRENGTH_I, surface_measured=True)
    assert measured < plans
    assert measured == pytest.approx(1.25)


def test_measuring_the_surface_does_not_touch_the_component_factor() -> None:
    plans_dc, _ = fac.dead_load_factors(fac.STRENGTH_I)
    measured_dc, _ = fac.dead_load_factors(fac.STRENGTH_I, surface_measured=True)
    assert measured_dc == pytest.approx(plans_dc)


def test_service_factors_are_unity() -> None:
    dc, dw = fac.dead_load_factors(fac.SERVICE_II)
    assert dc == pytest.approx(1.0)
    assert dw == pytest.approx(1.0)


def test_measuring_the_surface_changes_nothing_at_service() -> None:
    assert fac.dead_load_factors(fac.SERVICE_II, surface_measured=True) == pytest.approx(
        fac.dead_load_factors(fac.SERVICE_II)
    )


def test_an_unknown_limit_state_lists_the_known_ones() -> None:
    with pytest.raises(InputError, match="unknown limit state"):
        fac.dead_load_factors("extreme_ii")


@pytest.mark.parametrize(
    "limit_state,level,expected",
    [
        (fac.STRENGTH_I, fac.INVENTORY, 1.75),
        (fac.STRENGTH_I, fac.OPERATING, 1.35),
        (fac.SERVICE_II, fac.INVENTORY, 1.30),
        (fac.SERVICE_II, fac.OPERATING, 1.00),
    ],
)
def test_the_design_live_factors_are_the_published_ones(
    limit_state: str, level: str, expected: float
) -> None:
    assert fac.design_live_factor(limit_state, level) == pytest.approx(expected)


def test_operating_is_always_kinder_than_inventory() -> None:
    for limit_state in fac.LIMIT_STATES:
        operating = fac.design_live_factor(limit_state, fac.OPERATING)
        inventory = fac.design_live_factor(limit_state, fac.INVENTORY)
        assert operating < inventory


def test_an_unknown_rating_level_is_refused() -> None:
    with pytest.raises(InputError, match="unknown rating level"):
        fac.design_live_factor(fac.STRENGTH_I, "posting")


def test_an_unknown_limit_state_is_refused_by_the_live_factor() -> None:
    with pytest.raises(InputError, match="unknown limit state"):
        fac.design_live_factor("fatigue_i", fac.INVENTORY)


@pytest.mark.parametrize("adtt,expected", [(100.0, 1.40), (1000.0, 1.65), (5000.0, 1.80)])
def test_the_legal_factor_hits_the_published_points(adtt: float, expected: float) -> None:
    assert fac.legal_live_factor(adtt) == pytest.approx(expected)


def test_below_the_first_point_the_factor_flattens() -> None:
    assert fac.legal_live_factor(0.0) == pytest.approx(1.40)
    assert fac.legal_live_factor(50.0) == pytest.approx(1.40)


def test_above_the_last_point_the_factor_flattens() -> None:
    assert fac.legal_live_factor(20000.0) == pytest.approx(1.80)


def test_the_factor_interpolates_between_the_points() -> None:
    got = fac.legal_live_factor(550.0)
    assert got == pytest.approx(1.40 + (1.65 - 1.40) * 450.0 / 900.0)


def test_interpolating_beats_rounding_to_a_bracket() -> None:
    # Rounding 3000 down to the 1000 point loses five percent of the factor.
    interpolated = fac.legal_live_factor(3000.0)
    assert interpolated > fac.legal_live_factor(1000.0)
    assert interpolated < fac.legal_live_factor(5000.0)


def test_the_factor_never_falls_as_traffic_rises() -> None:
    values = [fac.legal_live_factor(a) for a in (0.0, 100.0, 500.0, 1000.0, 3000.0, 9000.0)]
    assert values == sorted(values)


def test_negative_truck_traffic_is_refused() -> None:
    with pytest.raises(InputError, match="is negative"):
        fac.legal_live_factor(-1.0)


@pytest.mark.parametrize("condition,expected", [("good", 1.00), ("fair", 0.95), ("poor", 0.85)])
def test_the_condition_factors_are_the_published_ones(condition: str, expected: float) -> None:
    assert fac.condition_factor(condition) == pytest.approx(expected)


def test_condition_lookup_forgives_case() -> None:
    assert fac.condition_factor(" POOR ") == pytest.approx(0.85)


def test_an_unknown_condition_is_refused() -> None:
    with pytest.raises(InputError, match="unknown member condition"):
        fac.condition_factor("serviceable")


@pytest.mark.parametrize(
    "redundancy,expected", [("redundant", 1.00), ("limited", 0.90), ("non_redundant", 0.85)]
)
def test_the_system_factors_are_the_published_ones(redundancy: str, expected: float) -> None:
    assert fac.system_factor(redundancy) == pytest.approx(expected)


def test_an_unknown_redundancy_is_refused() -> None:
    with pytest.raises(InputError, match="unknown redundancy"):
        fac.system_factor("two girder")


def test_a_good_redundant_member_loses_nothing() -> None:
    factors = fac.resistance_factors("good", "redundant")
    assert factors.product == pytest.approx(1.0)
    assert not factors.is_floored


def test_a_fair_limited_member_loses_a_little() -> None:
    factors = fac.resistance_factors("fair", "limited")
    assert factors.product == pytest.approx(0.95 * 0.90)
    assert not factors.is_floored


def test_a_poor_non_redundant_member_hits_the_floor() -> None:
    factors = fac.resistance_factors("poor", "non_redundant")
    assert factors.is_floored
    assert factors.product == pytest.approx(0.85)


def test_the_floor_stops_the_two_reductions_stacking() -> None:
    factors = fac.resistance_factors("poor", "non_redundant")
    unfloored = 0.85 * 0.85
    assert factors.product > unfloored


def test_the_resistance_factor_is_applied_after_the_floor() -> None:
    factors = ResistanceFactors(condition=0.85, system=0.85, resistance=0.90)
    assert factors.product == pytest.approx(0.85 * 0.90)


def test_a_resistance_factor_below_one_lowers_the_product() -> None:
    full = fac.resistance_factors("good", "redundant", resistance=1.00)
    reduced = fac.resistance_factors("good", "redundant", resistance=0.90)
    assert reduced.product < full.product


@pytest.mark.parametrize(
    "kwargs",
    [
        {"condition": 0.0},
        {"condition": 1.1},
        {"system": -0.5},
        {"resistance": 0.0},
    ],
)
def test_a_factor_outside_zero_to_one_is_refused(kwargs: dict[str, float]) -> None:
    base = {"condition": 1.0, "system": 1.0, "resistance": 1.0}
    with pytest.raises(InputError, match="outside zero to one"):
        ResistanceFactors(**{**base, **kwargs})
