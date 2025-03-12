"""Influence lines, and the jump in the shear line that every reading of it
has to account for."""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.loads.influence import (
    InfluenceLine,
    line,
    simple_moment,
    simple_reaction,
    simple_shear,
)

pytestmark = pytest.mark.loads


def test_midspan_moment_peaks_at_a_quarter_of_the_span() -> None:
    il = simple_moment(80.0, 40.0)
    assert il.at(40.0) == pytest.approx(20.0)
    assert il.peak == pytest.approx(20.0)


def test_the_moment_peak_is_ab_over_l() -> None:
    il = simple_moment(100.0, 30.0)
    assert il.at(30.0) == pytest.approx(30.0 * 70.0 / 100.0)


def test_moment_is_zero_at_both_supports() -> None:
    il = simple_moment(80.0, 32.0)
    assert il.at(0.0) == pytest.approx(0.0)
    assert il.at(80.0) == pytest.approx(0.0)


def test_moment_interpolates_linearly_on_each_leg() -> None:
    il = simple_moment(100.0, 40.0)
    assert il.at(20.0) == pytest.approx(il.at(40.0) / 2.0)
    assert il.at(70.0) == pytest.approx(il.at(40.0) / 2.0)


def test_a_load_off_the_span_does_nothing() -> None:
    il = simple_moment(80.0, 40.0)
    assert il.at(-3.0) == 0.0
    assert il.at(83.0) == 0.0


def test_the_moment_line_area_is_the_familiar_l_squared_over_eight() -> None:
    # A uniform unit load over a simple span gives wL^2/8 at midspan, so the
    # area under the midspan moment line has to be that.
    il = simple_moment(80.0, 40.0)
    assert il.area() == pytest.approx(80.0**2 / 8.0)


def test_the_shear_line_jumps_by_one_at_the_section() -> None:
    il = simple_shear(80.0, 30.0)
    assert il.jump_at(30.0) == pytest.approx(1.0)


def test_the_shear_ordinates_at_the_section_are_the_two_span_fractions() -> None:
    il = simple_shear(80.0, 30.0)
    assert il.at_left(30.0) == pytest.approx(-30.0 / 80.0)
    assert il.at(30.0) == pytest.approx(50.0 / 80.0)


def test_the_worst_reading_at_a_jump_is_the_larger_one() -> None:
    il = simple_shear(80.0, 30.0)
    assert il.worst_at(30.0) == pytest.approx(50.0 / 80.0)


def test_the_worst_reading_keeps_the_sign_of_the_larger_side() -> None:
    il = simple_shear(80.0, 60.0)
    assert il.worst_at(60.0) == pytest.approx(-60.0 / 80.0)


def test_a_continuous_line_has_no_jump() -> None:
    il = simple_moment(80.0, 30.0)
    assert il.jump_at(30.0) == pytest.approx(0.0)
    assert il.worst_at(30.0) == pytest.approx(il.at(30.0))


def test_end_shear_is_a_full_triangle_from_one() -> None:
    il = simple_shear(80.0, 0.0)
    assert il.at(0.0) == pytest.approx(1.0)
    assert il.at(40.0) == pytest.approx(0.5)
    assert il.at(80.0) == pytest.approx(0.0)


def test_shear_at_the_far_end_is_a_full_negative_triangle() -> None:
    il = simple_shear(80.0, 80.0)
    assert il.at_left(80.0) == pytest.approx(-1.0)
    assert il.at(40.0) == pytest.approx(-0.5)


def test_the_shear_line_areas_split_at_the_section() -> None:
    il = simple_shear(80.0, 30.0)
    assert il.positive_area() == pytest.approx(50.0 * (50.0 / 80.0) / 2.0)
    assert il.negative_area() == pytest.approx(-30.0 * (30.0 / 80.0) / 2.0)


def test_areas_add_up_to_the_signed_area() -> None:
    il = simple_shear(80.0, 30.0)
    assert il.positive_area() + il.negative_area() == pytest.approx(il.area())


def test_a_purely_positive_line_has_no_negative_area() -> None:
    il = simple_moment(80.0, 40.0)
    assert il.negative_area() == pytest.approx(0.0)
    assert il.positive_area() == pytest.approx(il.area())


def test_a_segment_crossing_the_axis_is_split_at_the_crossing() -> None:
    il = line("crossing", [(0.0, -1.0), (10.0, 1.0)])
    assert il.positive_area() == pytest.approx(2.5)
    assert il.negative_area() == pytest.approx(-2.5)
    assert il.area() == pytest.approx(0.0)


def test_the_left_reaction_line_runs_from_one_to_zero() -> None:
    il = simple_reaction(80.0)
    assert il.at(0.0) == pytest.approx(1.0)
    assert il.at(80.0) == pytest.approx(0.0)
    assert il.area() == pytest.approx(40.0)


def test_the_right_reaction_line_is_the_mirror() -> None:
    il = simple_reaction(80.0, left=False)
    assert il.at(0.0) == pytest.approx(0.0)
    assert il.at(80.0) == pytest.approx(1.0)


def test_scaling_multiplies_every_ordinate() -> None:
    il = simple_moment(80.0, 40.0).scaled(2.0)
    assert il.peak == pytest.approx(40.0)
    assert il.area() == pytest.approx(2.0 * 80.0**2 / 8.0)


def test_the_line_reports_its_extent() -> None:
    il = simple_moment(96.0, 40.0)
    assert il.start_ft == pytest.approx(0.0)
    assert il.end_ft == pytest.approx(96.0)
    assert il.length_ft == pytest.approx(96.0)


def test_the_trough_of_a_shear_line_is_the_left_ordinate() -> None:
    il = simple_shear(80.0, 30.0)
    assert il.trough == pytest.approx(-30.0 / 80.0)


def test_stations_and_ordinates_must_match_in_count() -> None:
    with pytest.raises(InputError, match="3 stations against 2 ordinates"):
        InfluenceLine("bad", (0.0, 1.0, 2.0), (0.0, 1.0))


def test_a_line_with_one_point_is_refused() -> None:
    with pytest.raises(InputError, match="at least two points"):
        line("bad", [(0.0, 0.0)])


def test_stations_running_backwards_are_refused() -> None:
    with pytest.raises(InputError, match="run backwards"):
        line("bad", [(0.0, 0.0), (10.0, 1.0), (5.0, 0.0)])


def test_a_line_needs_a_label() -> None:
    with pytest.raises(InputError, match="needs a label"):
        line(" ", [(0.0, 0.0), (1.0, 1.0)])


@pytest.mark.parametrize("section_ft", [-1.0, 81.0])
def test_a_section_off_the_span_is_refused(section_ft: float) -> None:
    with pytest.raises(InputError, match="is not on a 80 ft span"):
        simple_moment(80.0, section_ft)


def test_a_span_with_no_length_is_refused() -> None:
    with pytest.raises(InputError, match="is not a span"):
        simple_shear(0.0, 0.0)


def test_a_reaction_line_needs_a_span() -> None:
    with pytest.raises(InputError, match="is not a span"):
        simple_reaction(-10.0)
