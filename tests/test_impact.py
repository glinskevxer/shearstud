"""Dynamic load allowance, and the lane load that never gets any."""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.loads import impact

pytestmark = pytest.mark.loads


@pytest.mark.parametrize(
    "state,expected",
    [
        (impact.STATE_STRENGTH, 0.33),
        (impact.STATE_SERVICE, 0.33),
        (impact.STATE_FATIGUE, 0.15),
        (impact.STATE_DECK_JOINT, 0.75),
    ],
)
def test_the_base_allowances_are_the_published_ones(state: str, expected: float) -> None:
    assert impact.allowance_frac(state) == pytest.approx(expected)


def test_fatigue_gets_less_than_half_the_strength_allowance() -> None:
    fatigue = impact.allowance_frac(impact.STATE_FATIGUE)
    strength = impact.allowance_frac(impact.STATE_STRENGTH)
    assert fatigue < strength / 2.0


def test_a_deck_joint_gets_the_most() -> None:
    joint = impact.allowance_frac(impact.STATE_DECK_JOINT)
    assert all(joint >= impact.allowance_frac(s) for s in impact.STATES)


def test_an_unknown_limit_state_lists_the_known_ones() -> None:
    with pytest.raises(InputError, match="unknown limit state"):
        impact.allowance_frac("extreme")


@pytest.mark.parametrize(
    "surface,expected",
    [
        (impact.SURFACE_SMOOTH, 0.10),
        (impact.SURFACE_MINOR, 0.20),
        (impact.SURFACE_ROUGH, 0.33),
    ],
)
def test_the_legal_allowances_follow_the_surface(surface: str, expected: float) -> None:
    assert impact.legal_allowance_frac(surface) == pytest.approx(expected)


def test_a_rough_surface_gets_no_reduction_at_all() -> None:
    rough = impact.legal_allowance_frac(impact.SURFACE_ROUGH)
    assert rough == pytest.approx(impact.allowance_frac(impact.STATE_STRENGTH))


def test_a_smooth_surface_is_worth_a_third_of_the_allowance() -> None:
    smooth = impact.legal_allowance_frac(impact.SURFACE_SMOOTH)
    assert smooth < impact.allowance_frac(impact.STATE_STRENGTH) / 3.0 + 1e-9


def test_the_surfaces_get_worse_in_order() -> None:
    values = [impact.legal_allowance_frac(s) for s in impact.SURFACES]
    assert values == sorted(values)


def test_an_unknown_surface_is_refused() -> None:
    with pytest.raises(InputError, match="unknown riding surface"):
        impact.legal_allowance_frac("gravel")


def test_no_fill_leaves_the_allowance_alone() -> None:
    got = impact.buried_allowance_frac(impact.STATE_STRENGTH, 0.0)
    assert got == pytest.approx(0.33)


def test_half_the_cutoff_depth_halves_the_allowance() -> None:
    got = impact.buried_allowance_frac(impact.STATE_STRENGTH, impact.BURIAL_CUTOFF_FT / 2.0)
    assert got == pytest.approx(0.165)


def test_deep_fill_kills_the_allowance_entirely() -> None:
    assert impact.buried_allowance_frac(impact.STATE_STRENGTH, 12.0) == 0.0
    assert impact.buried_allowance_frac(impact.STATE_STRENGTH, impact.BURIAL_CUTOFF_FT) == 0.0


def test_fill_reduces_the_fatigue_allowance_too() -> None:
    got = impact.buried_allowance_frac(impact.STATE_FATIGUE, 4.0)
    assert got == pytest.approx(0.075)


def test_negative_fill_is_refused() -> None:
    with pytest.raises(InputError, match="is negative"):
        impact.buried_allowance_frac(impact.STATE_STRENGTH, -1.0)


def test_applying_the_allowance_scales_the_effect() -> None:
    assert impact.apply(1000.0, 0.33) == pytest.approx(1330.0)


def test_a_zero_allowance_leaves_the_effect_alone() -> None:
    assert impact.apply(1000.0, 0.0) == pytest.approx(1000.0)


def test_a_negative_allowance_is_refused() -> None:
    with pytest.raises(InputError, match="is negative"):
        impact.apply(1000.0, -0.1)


def test_the_allowance_lands_on_the_truck_and_not_the_lane() -> None:
    got = impact.combine_truck_and_lane(1000.0, 400.0, 0.33)
    assert got == pytest.approx(1330.0 + 400.0)


def test_giving_the_lane_load_impact_would_have_shown_a_different_number() -> None:
    correct = impact.combine_truck_and_lane(1000.0, 400.0, 0.33)
    wrong = (1000.0 + 400.0) * 1.33
    assert wrong > correct


def test_combining_with_no_lane_load_is_just_the_truck() -> None:
    assert impact.combine_truck_and_lane(1000.0, 0.0, 0.15) == pytest.approx(1150.0)


def test_a_negative_effect_keeps_its_sign_through_the_allowance() -> None:
    assert impact.apply(-800.0, 0.33) == pytest.approx(-1064.0)
