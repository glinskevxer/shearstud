"""Section properties, checked against shapes whose answers are known by hand."""

from __future__ import annotations

import pytest

from shearstud.errors import GeometryError
from shearstud.geometry.plate import Plate, flange, web
from shearstud.geometry.section import Section

pytestmark = pytest.mark.geometry


def solid_bar(width_in: float = 6.0, depth_in: float = 12.0) -> Section:
    """One plate, so every property has a closed form to compare against."""
    return Section("bar", (Plate("bar", width_in, depth_in, depth_in / 2.0),))


def symmetric_girder() -> Section:
    """A doubly symmetric welded plate girder, 54 inch web, 14 by 1 flanges."""
    return Section(
        "PG54",
        (
            flange("bottom", width_in=14.0, thickness_in=1.0, y_center_in=0.5),
            web("web", thickness_in=0.5, depth_in=54.0, y_center_in=28.0),
            flange("top", width_in=14.0, thickness_in=1.0, y_center_in=55.5),
        ),
    )


def singly_symmetric_girder() -> Section:
    """The same girder with a heavier bottom flange, as a positive moment
    region is usually detailed."""
    return Section(
        "PG54h",
        (
            flange("bottom", width_in=18.0, thickness_in=1.5, y_center_in=0.75),
            web("web", thickness_in=0.5, depth_in=54.0, y_center_in=28.5),
            flange("top", width_in=14.0, thickness_in=1.0, y_center_in=56.0),
        ),
    )


def test_a_solid_bar_matches_the_closed_form() -> None:
    s = solid_bar()
    assert s.area_in2 == pytest.approx(72.0)
    assert s.centroid_in == pytest.approx(6.0)
    assert s.inertia_in4 == pytest.approx(6.0 * 12.0**3 / 12.0)
    assert s.section_modulus_top_in3 == pytest.approx(6.0 * 12.0**2 / 6.0)


def test_a_solid_bar_has_equal_moduli_top_and_bottom() -> None:
    s = solid_bar()
    assert s.section_modulus_top_in3 == pytest.approx(s.section_modulus_bottom_in3)


def test_radius_of_gyration_of_a_bar_is_depth_over_root_twelve() -> None:
    s = solid_bar(depth_in=12.0)
    assert s.radius_of_gyration_in == pytest.approx(12.0 / 12.0**0.5)


def test_a_symmetric_girder_puts_the_axis_at_mid_depth() -> None:
    s = symmetric_girder()
    assert s.depth_in == pytest.approx(56.0)
    assert s.centroid_in == pytest.approx(28.0)
    assert s.c_top_in == pytest.approx(s.c_bottom_in)


def test_a_symmetric_girder_area_is_the_sum_of_its_plates() -> None:
    s = symmetric_girder()
    assert s.area_in2 == pytest.approx(14.0 + 27.0 + 14.0)


def test_a_heavier_bottom_flange_pulls_the_axis_down() -> None:
    plain = symmetric_girder()
    heavy = singly_symmetric_girder()
    assert heavy.centroid_in < heavy.depth_in / 2.0
    assert heavy.c_bottom_in < plain.c_bottom_in


def test_the_bottom_modulus_is_the_larger_one_when_the_axis_is_low() -> None:
    s = singly_symmetric_girder()
    assert s.section_modulus_bottom_in3 > s.section_modulus_top_in3


def test_the_flanges_earn_their_keep_through_the_transfer_term() -> None:
    # The web carries its own inertia; the flanges are almost all transfer.
    s = symmetric_girder()
    flange_own = s.plate("top").inertia_own_in4 + s.plate("bottom").inertia_own_in4
    web_own = s.plate("web").inertia_own_in4
    assert s.inertia_in4 > web_own + flange_own
    assert s.inertia_in4 - web_own - flange_own > 100.0 * flange_own


def test_the_first_moment_is_zero_at_both_extreme_fibres() -> None:
    s = symmetric_girder()
    assert s.first_moment_above_in3(s.y_top_in) == pytest.approx(0.0)
    assert s.first_moment_above_in3(s.y_bottom_in) == pytest.approx(0.0, abs=1e-9)


def test_the_first_moment_peaks_at_the_neutral_axis() -> None:
    s = symmetric_girder()
    at_axis = s.first_moment_above_in3(s.centroid_in)
    for y_in in (10.0, 20.0, 36.0, 50.0):
        assert s.first_moment_above_in3(y_in) <= at_axis + 1e-9


def test_the_first_moment_is_continuous_across_a_plate_boundary() -> None:
    s = symmetric_girder()
    just_below = s.first_moment_above_in3(1.0 - 1e-6)
    just_above = s.first_moment_above_in3(1.0 + 1e-6)
    assert just_below == pytest.approx(just_above, abs=1e-3)


def test_rebasing_moves_the_datum_without_moving_the_steel() -> None:
    raised = Section(
        "raised",
        (
            flange("bottom", width_in=14.0, thickness_in=1.0, y_center_in=100.5),
            web("web", thickness_in=0.5, depth_in=54.0, y_center_in=128.0),
            flange("top", width_in=14.0, thickness_in=1.0, y_center_in=155.5),
        ),
    )
    rebased = raised.rebased()
    assert rebased.y_bottom_in == pytest.approx(0.0)
    assert rebased.inertia_in4 == pytest.approx(raised.inertia_in4)
    assert rebased.section_modulus_bottom_in3 == pytest.approx(raised.section_modulus_bottom_in3)


def test_rebasing_an_already_based_section_returns_it_unchanged() -> None:
    s = symmetric_girder()
    assert s.rebased() is s


def test_a_plate_can_be_fetched_by_label() -> None:
    s = symmetric_girder()
    assert s.plate("web").height_in == pytest.approx(54.0)


def test_asking_for_a_plate_that_is_not_there_raises() -> None:
    s = symmetric_girder()
    with pytest.raises(GeometryError, match="no plate labelled"):
        s.plate("cover")


def test_an_empty_section_is_refused() -> None:
    with pytest.raises(GeometryError, match="at least one plate"):
        Section("empty", ())


def test_duplicate_plate_labels_are_refused() -> None:
    with pytest.raises(GeometryError, match="duplicate plate label"):
        Section(
            "dup",
            (
                flange("f", width_in=10.0, thickness_in=1.0, y_center_in=0.5),
                flange("f", width_in=10.0, thickness_in=1.0, y_center_in=20.5),
            ),
        )


def test_a_section_needs_a_label() -> None:
    with pytest.raises(GeometryError, match="needs a label"):
        Section("", (flange("f", width_in=10.0, thickness_in=1.0, y_center_in=0.5),))


def test_a_section_iterates_and_counts_its_plates() -> None:
    s = symmetric_girder()
    assert len(s) == 3
    assert [p.label for p in s] == ["bottom", "web", "top"]


def test_the_area_below_the_bottom_fibre_is_nothing() -> None:
    s = symmetric_girder()
    assert s.area_below_in2(s.y_bottom_in) == pytest.approx(0.0)


def test_the_area_below_the_top_fibre_is_everything() -> None:
    s = symmetric_girder()
    assert s.area_below_in2(s.y_top_in) == pytest.approx(s.area_in2)


def test_the_area_below_mid_depth_is_half_of_a_symmetric_section() -> None:
    s = symmetric_girder()
    assert s.area_below_in2(s.depth_in / 2.0) == pytest.approx(s.area_in2 / 2.0)


def test_the_area_sweep_never_goes_backwards() -> None:
    s = singly_symmetric_girder()
    levels = [i * s.depth_in / 20.0 for i in range(21)]
    areas = [s.area_below_in2(y) for y in levels]
    assert areas == sorted(areas)


def test_a_plate_that_straddles_the_level_is_split() -> None:
    s = symmetric_girder()
    half_flange = s.area_below_in2(0.5)
    assert half_flange == pytest.approx(14.0 * 0.5)


def test_the_width_at_a_flange_is_the_flange_width() -> None:
    s = symmetric_girder()
    assert s.width_at_in(0.5) == pytest.approx(14.0)


def test_the_width_in_the_web_is_the_web_thickness() -> None:
    s = symmetric_girder()
    assert s.width_at_in(28.0) == pytest.approx(0.5)


def test_the_width_at_a_plate_boundary_counts_both_plates() -> None:
    s = symmetric_girder()
    assert s.width_at_in(1.0) == pytest.approx(14.5)


def test_the_width_off_the_section_is_nothing() -> None:
    s = symmetric_girder()
    assert s.width_at_in(s.y_top_in + 5.0) == pytest.approx(0.0)


def test_the_plate_edges_are_sorted_and_distinct() -> None:
    edges = symmetric_girder().plate_edges_in()
    assert list(edges) == sorted(set(edges))


def test_the_plate_edges_span_the_whole_section() -> None:
    s = symmetric_girder()
    edges = s.plate_edges_in()
    assert edges[0] == pytest.approx(s.y_bottom_in)
    assert edges[-1] == pytest.approx(s.y_top_in)


def test_a_touching_stack_shares_its_boundaries() -> None:
    # Bottom flange top and web bottom are the same height, so four plate
    # boundaries collapse to four distinct edges rather than six.
    assert len(symmetric_girder().plate_edges_in()) == 4
