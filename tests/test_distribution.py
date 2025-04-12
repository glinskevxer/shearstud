"""Distribution factors, including the presence factor trap."""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.loads import distribution as dist
from shearstud.loads.distribution import GirderStiffness

pytestmark = pytest.mark.loads


def stiffness(inertia_in4: float = 30000.0) -> GirderStiffness:
    return GirderStiffness(
        inertia_in4=inertia_in4,
        area_in2=60.0,
        eccentricity_in=32.0,
        modular_ratio=8.0,
    )


def test_the_stiffness_parameter_is_the_transfer_plus_the_inertia() -> None:
    k = stiffness()
    assert k.kg_in4 == pytest.approx(8.0 * (30000.0 + 60.0 * 32.0**2))


def test_a_deeper_girder_has_a_larger_stiffness_parameter() -> None:
    assert stiffness(50000.0).kg_in4 > stiffness(20000.0).kg_in4


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"inertia_in4": 0.0}, "inertia"),
        ({"area_in2": -1.0}, "area"),
        ({"modular_ratio": 0.0}, "modular ratio"),
    ],
)
def test_a_bad_stiffness_input_is_refused(kwargs: dict[str, float], message: str) -> None:
    base = {
        "inertia_in4": 30000.0,
        "area_in2": 60.0,
        "eccentricity_in": 32.0,
        "modular_ratio": 8.0,
    }
    with pytest.raises(InputError, match=message):
        GirderStiffness(**{**base, **kwargs})


@pytest.mark.parametrize("lanes,expected", [(1, 1.20), (2, 1.00), (3, 0.85), (4, 0.65), (7, 0.65)])
def test_the_presence_factors_are_the_published_ones(lanes: int, expected: float) -> None:
    assert dist.presence_factor(lanes) == pytest.approx(expected)


def test_no_lanes_loaded_is_not_a_load_case() -> None:
    with pytest.raises(InputError, match="not a load case"):
        dist.presence_factor(0)


def test_applying_presence_multiplies_by_the_factor() -> None:
    assert dist.apply_presence(0.5, 1) == pytest.approx(0.6)
    assert dist.apply_presence(0.5, 3) == pytest.approx(0.425)


def test_a_typical_interior_girder_lands_where_a_rating_sheet_puts_it() -> None:
    g = dist.interior_moment(7.5, 100.0, 8.0, stiffness(), 5, lanes_loaded=2)
    assert 0.55 < g < 0.80


def test_two_lanes_loaded_beats_one_on_a_normal_spacing() -> None:
    one = dist.interior_moment(7.5, 100.0, 8.0, stiffness(), 5, lanes_loaded=1)
    two = dist.interior_moment(7.5, 100.0, 8.0, stiffness(), 5, lanes_loaded=2)
    assert two > one


def test_a_wider_spacing_puts_more_load_on_each_girder() -> None:
    tight = dist.interior_moment(6.0, 100.0, 8.0, stiffness(), 5, lanes_loaded=2)
    wide = dist.interior_moment(12.0, 100.0, 8.0, stiffness(), 5, lanes_loaded=2)
    assert wide > tight


def test_a_longer_span_spreads_the_load_out() -> None:
    short = dist.interior_moment(7.5, 40.0, 8.0, stiffness(), 5, lanes_loaded=2)
    long = dist.interior_moment(7.5, 200.0, 8.0, stiffness(), 5, lanes_loaded=2)
    assert long < short


def test_a_stiffer_girder_attracts_more_load() -> None:
    soft = dist.interior_moment(7.5, 100.0, 8.0, stiffness(15000.0), 5, lanes_loaded=2)
    stiff = dist.interior_moment(7.5, 100.0, 8.0, stiffness(90000.0), 5, lanes_loaded=2)
    assert stiff > soft


def test_the_stiffness_term_is_a_weak_one() -> None:
    # It enters to the tenth power, so a six fold change in Kg moves the factor
    # by well under a fifth. That is why the equations tolerate a rough Kg.
    soft = dist.interior_moment(7.5, 100.0, 8.0, stiffness(15000.0), 5, lanes_loaded=2)
    stiff = dist.interior_moment(7.5, 100.0, 8.0, stiffness(90000.0), 5, lanes_loaded=2)
    assert stiff / soft < 1.2


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"spacing_ft": 2.0}, "girder spacing"),
        ({"spacing_ft": 20.0}, "girder spacing"),
        ({"span_ft": 10.0}, "span"),
        ({"span_ft": 400.0}, "span"),
        ({"slab_in": 3.0}, "slab thickness"),
        ({"slab_in": 15.0}, "slab thickness"),
        ({"beams": 3}, "fewer than the 4"),
    ],
)
def test_outside_the_range_of_applicability_is_refused(
    kwargs: dict[str, float], message: str
) -> None:
    base = {
        "spacing_ft": 7.5,
        "span_ft": 100.0,
        "slab_in": 8.0,
        "stiffness": stiffness(),
        "beams": 5,
    }
    with pytest.raises(InputError, match=message):
        dist.interior_moment(**{**base, **kwargs}, lanes_loaded=2)  # type: ignore[arg-type]


def test_a_stiffness_parameter_off_the_chart_is_refused() -> None:
    huge = GirderStiffness(
        inertia_in4=4_000_000.0, area_in2=400.0, eccentricity_in=60.0, modular_ratio=8.0
    )
    with pytest.raises(InputError, match="stiffness parameter"):
        dist.interior_moment(7.5, 100.0, 8.0, huge, 5, lanes_loaded=2)


def test_shear_factors_do_not_read_the_stiffness_at_all() -> None:
    assert dist.interior_shear(7.5, lanes_loaded=1) == pytest.approx(0.36 + 7.5 / 25.0)


def test_the_two_lane_shear_equation_is_the_published_one() -> None:
    got = dist.interior_shear(9.0, lanes_loaded=2)
    assert got == pytest.approx(0.2 + 9.0 / 12.0 - (9.0 / 35.0) ** 2)


def test_two_lanes_beat_one_in_shear_on_a_normal_spacing() -> None:
    assert dist.interior_shear(7.5, lanes_loaded=2) > dist.interior_shear(7.5, lanes_loaded=1)


def test_a_shear_spacing_outside_the_range_is_refused() -> None:
    with pytest.raises(InputError, match="girder spacing"):
        dist.interior_shear(2.0, lanes_loaded=2)


def test_the_exterior_moment_correction_never_helps() -> None:
    assert dist.exterior_correction_moment(0.0) == pytest.approx(1.0)
    assert dist.exterior_correction_moment(-1.0) == pytest.approx(1.0)


def test_a_wide_overhang_makes_the_exterior_girder_work_harder() -> None:
    assert dist.exterior_correction_moment(5.0) > dist.exterior_correction_moment(2.0)


def test_the_shear_correction_is_a_different_fit_from_the_moment_one() -> None:
    assert dist.exterior_correction_shear(4.0) != dist.exterior_correction_moment(4.0)


def test_the_shear_correction_also_never_helps() -> None:
    assert dist.exterior_correction_shear(0.0) == pytest.approx(1.0)


@pytest.mark.parametrize("fn", [dist.exterior_correction_moment, dist.exterior_correction_shear])
def test_a_curb_distance_off_the_chart_is_refused(fn: object) -> None:
    with pytest.raises(InputError, match="outside -1.0 to 5.5"):
        fn(9.0)  # type: ignore[operator]


def test_the_lever_rule_puts_a_wheel_over_the_girder_fully_on_it() -> None:
    assert dist.lever_rule(7.5, [0.0]) == pytest.approx(1.0)


def test_the_lever_rule_puts_a_wheel_over_the_hinge_nowhere() -> None:
    assert dist.lever_rule(7.5, [7.5]) == pytest.approx(0.0)


def test_the_lever_rule_interpolates_between_the_two() -> None:
    assert dist.lever_rule(8.0, [2.0]) == pytest.approx(0.75)


def test_a_wheel_past_the_interior_girder_unloads_the_exterior_one() -> None:
    assert dist.lever_rule(7.5, [9.5]) < 0.0


def test_two_wheels_add_up() -> None:
    assert dist.lever_rule(8.0, [2.0, 8.0]) == pytest.approx(0.75)


def test_the_lever_rule_still_needs_the_presence_factor() -> None:
    wheel_lines = dist.lever_rule(8.0, [1.0, 7.0])
    lanes = wheel_lines / 2.0
    assert dist.apply_presence(lanes, 1) == pytest.approx(lanes * 1.2)


def test_a_lever_rule_with_no_wheels_is_refused() -> None:
    with pytest.raises(InputError, match="at least one wheel"):
        dist.lever_rule(7.5, [])


def test_a_lever_rule_with_no_spacing_is_refused() -> None:
    with pytest.raises(InputError, match="not a spacing"):
        dist.lever_rule(0.0, [1.0])
