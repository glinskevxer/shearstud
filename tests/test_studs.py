"""Shear connectors: the two checks and why they cannot be combined."""

from __future__ import annotations

import math

import pytest

from shearstud.errors import InputError
from shearstud.geometry.composite import CompositeGirder, DeckSlab
from shearstud.geometry.plate import Plate
from shearstud.geometry.section import Section
from shearstud.rating import studs as st
from shearstud.rating.studs import StudSpec

pytestmark = pytest.mark.rating


def stud(diameter_in: float = 0.875, height_in: float = 6.0) -> StudSpec:
    return StudSpec(diameter_in=diameter_in, height_in=height_in, tensile_strength_ksi=60.0)


def test_the_shank_area_is_a_circle() -> None:
    assert stud(0.875).area_in2 == pytest.approx(math.pi * 0.875**2 / 4.0)


def test_a_stocked_diameter_is_standard() -> None:
    assert stud(0.75).is_standard
    assert not stud(0.8125).is_standard


def test_a_stud_that_is_not_tall_enough_is_refused() -> None:
    with pytest.raises(InputError, match="at least 3.5 in tall"):
        StudSpec(diameter_in=0.875, height_in=3.0, tensile_strength_ksi=60.0)


def test_a_stud_with_no_diameter_is_refused() -> None:
    with pytest.raises(InputError, match="is not a diameter"):
        StudSpec(diameter_in=0.0, height_in=6.0, tensile_strength_ksi=60.0)


def test_a_stud_with_no_strength_is_refused() -> None:
    with pytest.raises(InputError, match="is not a strength"):
        StudSpec(diameter_in=0.875, height_in=6.0, tensile_strength_ksi=0.0)


def test_a_bigger_stud_is_stronger() -> None:
    assert stud(1.0).strength_kip(4.0) > stud(0.625).strength_kip(4.0)


def test_a_stronger_deck_raises_the_concrete_bound() -> None:
    assert stud().strength_kip(6.0) > stud().strength_kip(3.0)


def test_a_weak_deck_is_governed_by_the_concrete() -> None:
    assert not stud().governed_by_steel(2.5)


def test_a_strong_deck_is_governed_by_the_steel() -> None:
    assert stud().governed_by_steel(8.0)


def test_the_steel_bound_caps_the_strength() -> None:
    # Past the crossover the strength stops rising with the concrete.
    weak = stud().strength_kip(8.0)
    strong = stud().strength_kip(12.0)
    assert weak == pytest.approx(strong)


def test_a_concrete_strength_of_zero_is_refused() -> None:
    with pytest.raises(InputError, match="is not a strength"):
        stud().strength_kip(0.0)


def test_the_fatigue_one_resistance_is_the_coefficient_times_d_squared() -> None:
    assert stud(0.875).fatigue_resistance_kip() == pytest.approx(5.5 * 0.875**2)


def test_the_fatigue_two_resistance_falls_with_the_cycle_count() -> None:
    short = stud().fatigue_resistance_kip(1.0e5)
    long = stud().fatigue_resistance_kip(1.0e7)
    assert short > long


def test_the_fatigue_two_resistance_has_a_floor() -> None:
    floored = stud().fatigue_resistance_kip(1.0e12)
    assert floored == pytest.approx(2.75 * 0.875**2)


def test_the_fatigue_two_resistance_beats_fatigue_one_at_a_short_life() -> None:
    assert stud().fatigue_resistance_kip(1.0e4) > stud().fatigue_resistance_kip()


def test_a_life_of_zero_cycles_is_refused() -> None:
    with pytest.raises(InputError, match="is not a life"):
        stud().fatigue_resistance_kip(0.0)


def test_the_shear_flow_is_zero_at_the_extreme_fibres(composite_girder: CompositeGirder) -> None:
    section = composite_girder.short_term
    assert st.shear_flow_kip_per_in(section, section.y_top_in, 100.0) == pytest.approx(0.0)
    assert st.shear_flow_kip_per_in(section, section.y_bottom_in, 100.0) == pytest.approx(
        0.0, abs=1e-9
    )


def test_the_shear_flow_peaks_at_the_neutral_axis(composite_girder: CompositeGirder) -> None:
    section = composite_girder.short_term
    at_axis = st.shear_flow_kip_per_in(section, section.centroid_in, 100.0)
    for y_in in (5.0, 20.0, 45.0, 60.0):
        assert st.shear_flow_kip_per_in(section, y_in, 100.0) <= at_axis + 1e-9


def test_the_shear_flow_is_linear_in_the_shear(composite_girder: CompositeGirder) -> None:
    section = composite_girder.short_term
    one = st.shear_flow_kip_per_in(section, 40.0, 100.0)
    two = st.shear_flow_kip_per_in(section, 40.0, 200.0)
    assert two == pytest.approx(2.0 * one)


def test_the_interface_flow_is_taken_at_the_top_of_the_steel(
    composite_girder: CompositeGirder,
) -> None:
    got = st.interface_flow_kip_per_in(composite_girder, 100.0)
    expected = st.shear_flow_kip_per_in(
        composite_girder.short_term, composite_girder.steel_top_in, 100.0
    )
    assert got == pytest.approx(expected)


def test_the_interface_flow_uses_the_short_term_section(
    composite_girder: CompositeGirder,
) -> None:
    short = st.interface_flow_kip_per_in(composite_girder, 100.0)
    long = st.shear_flow_kip_per_in(
        composite_girder.long_term, composite_girder.steel_top_in, 100.0
    )
    assert short != pytest.approx(long)


def test_the_interface_flow_is_positive_for_a_positive_shear(
    composite_girder: CompositeGirder,
) -> None:
    assert st.interface_flow_kip_per_in(composite_girder, 100.0) > 0.0


def test_a_bigger_shear_range_needs_a_tighter_pitch(
    composite_girder: CompositeGirder,
) -> None:
    light = st.required_pitch_in(composite_girder, 30.0, 3, stud())
    heavy = st.required_pitch_in(composite_girder, 90.0, 3, stud())
    assert heavy < light


def test_more_studs_in_a_row_allow_a_wider_pitch(
    composite_girder: CompositeGirder,
) -> None:
    two = st.required_pitch_in(composite_girder, 60.0, 2, stud())
    four = st.required_pitch_in(composite_girder, 60.0, 4, stud())
    assert four == pytest.approx(2.0 * two)


def test_a_zero_shear_range_gives_the_maximum_pitch(
    composite_girder: CompositeGirder,
) -> None:
    assert st.required_pitch_in(composite_girder, 0.0, 3, stud()) == pytest.approx(48.0)


def test_a_negative_shear_range_is_refused(composite_girder: CompositeGirder) -> None:
    with pytest.raises(InputError, match="is negative"):
        st.required_pitch_in(composite_girder, -10.0, 3, stud())


def test_a_row_of_no_studs_is_refused(composite_girder: CompositeGirder) -> None:
    with pytest.raises(InputError, match="is not a row"):
        st.required_pitch_in(composite_girder, 60.0, 0, stud())


def test_the_pitch_limits_scale_with_the_diameter() -> None:
    low, high = st.pitch_limits_in(stud(0.875))
    assert low == pytest.approx(6.0 * 0.875)
    assert high == pytest.approx(48.0)


def test_a_wide_required_pitch_is_clamped_to_the_maximum(
    composite_girder: CompositeGirder,
) -> None:
    assert st.usable_pitch_in(composite_girder, 1.0, 4, stud()) == pytest.approx(48.0)


def test_a_tight_required_pitch_is_clamped_to_the_minimum(
    composite_girder: CompositeGirder,
) -> None:
    tight = st.usable_pitch_in(composite_girder, 4000.0, 1, stud())
    assert tight == pytest.approx(6.0 * 0.875)


def test_a_shear_range_that_lands_inside_the_limits_is_not_clamped(
    composite_girder: CompositeGirder,
) -> None:
    low, high = st.pitch_limits_in(stud())
    inside = [
        shear_kip
        for shear_kip in (10.0, 20.0, 40.0, 60.0, 90.0, 140.0, 220.0)
        if low < st.required_pitch_in(composite_girder, shear_kip, 3, stud()) < high
    ]
    assert inside, "no shear range in the sweep produced an unclamped pitch"
    for shear_kip in inside:
        required = st.required_pitch_in(composite_girder, shear_kip, 3, stud())
        assert st.usable_pitch_in(composite_girder, shear_kip, 3, stud()) == pytest.approx(required)


def test_the_fatigue_one_threshold_is_the_tightest_of_the_three() -> None:
    threshold = stud().fatigue_resistance_kip()
    assert threshold < stud().fatigue_resistance_kip(1.0e6)
    assert threshold > stud().fatigue_resistance_kip(1.0e12)


def test_the_strength_check_counts_rows_not_spacing() -> None:
    rows = st.rows_needed_for_strength(800.0, stud(), 4.0, 3)
    assert isinstance(rows, int)
    assert rows > 0


def test_a_bigger_shear_needs_more_rows() -> None:
    few = st.rows_needed_for_strength(400.0, stud(), 4.0, 3)
    many = st.rows_needed_for_strength(1200.0, stud(), 4.0, 3)
    assert many > few


def test_the_row_count_rounds_up() -> None:
    per_row = 3 * stud().strength_kip(4.0)
    assert st.rows_needed_for_strength(per_row * 2.01, stud(), 4.0, 3) == 3


def test_no_shear_needs_no_rows() -> None:
    assert st.rows_needed_for_strength(0.0, stud(), 4.0, 3) == 0


def test_a_negative_total_shear_is_refused() -> None:
    with pytest.raises(InputError, match="is negative"):
        st.rows_needed_for_strength(-5.0, stud(), 4.0, 3)


def test_a_strength_row_of_no_studs_is_refused() -> None:
    with pytest.raises(InputError, match="is not a row"):
        st.rows_needed_for_strength(500.0, stud(), 4.0, 0)


def test_a_one_plate_section_still_carries_shear_flow() -> None:
    bar = Section("bar", (Plate("only", 6.0, 12.0, 6.0),))
    assert st.shear_flow_kip_per_in(bar, 6.0, 100.0) > 0.0


def test_the_deck_is_part_of_what_the_studs_hold(
    positive_moment_girder: Section, deck: DeckSlab
) -> None:
    girder = CompositeGirder(steel=positive_moment_girder, deck=deck)
    with_deck = abs(st.interface_flow_kip_per_in(girder, 100.0))
    assert with_deck > 0.0
