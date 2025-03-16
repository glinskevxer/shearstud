"""Continuous unit analysis, checked against results that can be looked up.

The two span beam has closed form answers for a point load at midspan and for
uniform load over both spans, and those are the checks that matter: they test
the three moment solve, the continuity correction and the influence line
sampling together.
"""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.loads import continuous
from shearstud.loads.influence import simple_moment, simple_shear

pytestmark = pytest.mark.loads

L = 100.0
TWO = [L, L]
THREE = [84.0, 105.0, 84.0]


def test_a_point_load_at_midspan_gives_three_pl_over_thirty_two() -> None:
    moments = continuous.support_moments(TWO, 0, L / 2.0)
    assert moments[1] == pytest.approx(-3.0 * L / 32.0)


def test_the_abutment_moments_are_zero() -> None:
    moments = continuous.support_moments(TWO, 0, L / 3.0)
    assert moments[0] == 0.0
    assert moments[-1] == 0.0


def test_a_load_over_a_support_bends_nothing() -> None:
    moments = continuous.support_moments(TWO, 0, L)
    assert moments[1] == pytest.approx(0.0)


def test_a_mirrored_load_gives_a_mirrored_support_moment() -> None:
    left = continuous.support_moments(TWO, 0, 0.4 * L)[1]
    right = continuous.support_moments(TWO, 1, 0.6 * L)[1]
    assert left == pytest.approx(right)


def test_a_single_span_unit_has_no_interior_supports() -> None:
    assert continuous.support_moments([L], 0, L / 2.0) == [0.0, 0.0]


def test_uniform_load_over_two_spans_gives_wl_squared_over_eight() -> None:
    il = continuous.continuous_support_moment(TWO, 1)
    assert il.area() == pytest.approx(-(L**2) / 8.0, rel=1e-3)


def test_uniform_load_over_two_spans_gives_the_end_reaction_of_three_eighths() -> None:
    reaction = continuous.continuous_shear(TWO, 0, 0.0)
    assert reaction.area() == pytest.approx(3.0 * L / 8.0, rel=1e-3)


def test_the_end_reaction_line_starts_at_one() -> None:
    reaction = continuous.continuous_shear(TWO, 0, 0.0)
    assert reaction.at(0.0) == pytest.approx(1.0)


def test_the_end_reaction_goes_negative_under_the_back_span() -> None:
    # A load in the far span lifts the near abutment, which is the whole reason
    # uplift has to be checked on unbalanced continuous units.
    reaction = continuous.continuous_shear(TWO, 0, 0.0)
    assert reaction.at(1.5 * L) < 0.0


def test_a_single_span_continuous_call_matches_the_simple_span_line() -> None:
    got = continuous.continuous_moment([L], 0, 0.4 * L, samples=400)
    want = simple_moment(L, 0.4 * L)
    for station_ft in (0.0, 10.0, 40.0, 55.0, 90.0, 100.0):
        assert got.at(station_ft) == pytest.approx(want.at(station_ft), abs=0.05)


def test_a_single_span_shear_call_matches_the_simple_span_line() -> None:
    got = continuous.continuous_shear([L], 0, 30.0, samples=400)
    want = simple_shear(L, 30.0)
    for station_ft in (0.0, 10.0, 29.0, 45.0, 80.0, 100.0):
        assert got.at(station_ft) == pytest.approx(want.at(station_ft), abs=0.02)


def test_the_shear_line_still_jumps_by_one_at_the_section() -> None:
    il = continuous.continuous_shear(TWO, 0, 40.0)
    assert il.jump_at(40.0) == pytest.approx(1.0, abs=1e-3)
    assert il.at_left(40.0) < 0.0 < il.at(40.0)


def test_midspan_moment_goes_negative_when_the_load_is_in_the_back_span() -> None:
    il = continuous.continuous_moment(TWO, 0, L / 2.0)
    assert il.at(L / 2.0) > 0.0
    assert il.at(1.5 * L) < 0.0


def test_continuity_cuts_the_midspan_moment_below_the_simple_span_value() -> None:
    joined = continuous.continuous_moment(TWO, 0, L / 2.0).at(L / 2.0)
    alone = simple_moment(L, L / 2.0).at(L / 2.0)
    assert joined < alone


def test_the_support_moment_line_is_negative_everywhere_it_is_loaded() -> None:
    il = continuous.continuous_support_moment(TWO, 1)
    for station_ft in (0.25 * L, 0.5 * L, 0.75 * L, 1.25 * L, 1.75 * L):
        assert il.at(station_ft) < 0.0


def test_a_symmetric_three_span_unit_has_symmetric_pier_moments() -> None:
    first = continuous.continuous_support_moment(THREE, 1)
    second = continuous.continuous_support_moment(THREE, 2)
    total_ft = sum(THREE)
    for station_ft in (20.0, 84.0, 136.5, 189.0, 250.0):
        assert first.at(station_ft) == pytest.approx(second.at(total_ft - station_ft), abs=1e-6)


def test_the_two_pier_moments_of_a_three_span_unit_are_both_negative() -> None:
    for support in (1, 2):
        il = continuous.continuous_support_moment(THREE, support)
        assert il.trough < 0.0


def test_shear_and_moment_agree_on_where_the_load_is() -> None:
    # Moment at a section is the integral of shear, so a load right at the
    # section produces the peak of both.
    moment = continuous.continuous_moment(THREE, 1, 52.5)
    assert moment.at(136.5) == pytest.approx(moment.peak, rel=1e-3)


def test_a_load_position_off_its_span_is_refused() -> None:
    with pytest.raises(InputError, match="is not on span 0"):
        continuous.support_moments(TWO, 0, L + 5.0)


def test_a_span_that_does_not_exist_is_refused() -> None:
    with pytest.raises(InputError, match="no span 4 in a 2 span unit"):
        continuous.support_moments(TWO, 4, 10.0)


def test_a_unit_with_no_spans_is_refused() -> None:
    with pytest.raises(InputError, match="at least one span"):
        continuous.support_moments([], 0, 0.0)


def test_a_span_with_no_length_is_refused() -> None:
    with pytest.raises(InputError, match="not a span"):
        continuous.support_moments([100.0, 0.0], 0, 10.0)


def test_too_few_samples_is_refused() -> None:
    with pytest.raises(InputError, match="too coarse"):
        continuous.continuous_moment(THREE, 0, 40.0, samples=8)


def test_an_exterior_support_is_not_an_interior_one() -> None:
    with pytest.raises(InputError, match="not an interior support"):
        continuous.continuous_support_moment(TWO, 0)


def test_the_last_support_is_not_an_interior_one() -> None:
    with pytest.raises(InputError, match="not an interior support"):
        continuous.continuous_support_moment(TWO, 2)
