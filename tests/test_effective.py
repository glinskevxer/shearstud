"""Effective flange width under both rules, including the case where the older
rule is the more generous one."""

from __future__ import annotations

import pytest

from shearstud.errors import GeometryError
from shearstud.geometry import effective
from shearstud.geometry.effective import DeckLayout
from shearstud.geometry.section import Section

pytestmark = pytest.mark.geometry


def interior(spacing_ft: float = 7.5, slab_in: float = 8.0) -> DeckLayout:
    return DeckLayout(
        girder_index=2,
        spacing_left_ft=spacing_ft,
        spacing_right_ft=spacing_ft,
        overhang_ft=0.0,
        slab_thickness_in=slab_in,
    )


def exterior(spacing_ft: float = 7.5, overhang_ft: float = 3.25) -> DeckLayout:
    return DeckLayout(
        girder_index=0,
        spacing_left_ft=0.0,
        spacing_right_ft=spacing_ft,
        overhang_ft=overhang_ft,
        slab_thickness_in=8.0,
    )


def test_an_interior_girder_is_not_exterior() -> None:
    assert not interior().is_exterior
    assert exterior().is_exterior


def test_the_tributary_width_of_an_interior_girder_is_the_spacing() -> None:
    assert effective.tributary_width_in(interior(7.5)) == pytest.approx(90.0)


def test_the_tributary_width_of_an_exterior_girder_adds_the_whole_overhang() -> None:
    layout = exterior(spacing_ft=7.5, overhang_ft=3.25)
    assert effective.tributary_width_in(layout) == pytest.approx((3.75 + 3.25) * 12.0)


def test_unequal_bays_average_out() -> None:
    layout = DeckLayout(
        girder_index=1,
        spacing_left_ft=6.0,
        spacing_right_ft=9.0,
        overhang_ft=0.0,
        slab_thickness_in=8.0,
    )
    assert layout.interior_half_width_ft == pytest.approx(7.5)
    assert layout.average_spacing_ft == pytest.approx(7.5)


def test_the_average_spacing_of_an_exterior_girder_ignores_the_overhang_side() -> None:
    assert exterior(spacing_ft=9.0).average_spacing_ft == pytest.approx(9.0)


def test_the_legacy_interior_rule_is_governed_by_spacing_on_a_long_span(
    symmetric_plate_girder: Section,
) -> None:
    # Quarter of a 120 foot span is 360 inches and the slab limit is over 100,
    # so the 90 inch spacing is the least of the three.
    width = effective.legacy_interior_width_in(interior(7.5), symmetric_plate_girder, 120.0)
    assert width == pytest.approx(90.0)


def test_the_legacy_interior_rule_is_governed_by_the_span_on_a_short_one(
    symmetric_plate_girder: Section,
) -> None:
    width = effective.legacy_interior_width_in(interior(12.0), symmetric_plate_girder, 25.0)
    assert width == pytest.approx(75.0)


def test_the_legacy_interior_rule_is_governed_by_the_slab_on_a_thin_deck(
    symmetric_plate_girder: Section,
) -> None:
    layout = interior(spacing_ft=14.0, slab_in=6.0)
    width = effective.legacy_interior_width_in(layout, symmetric_plate_girder, 120.0)
    assert width == pytest.approx(12.0 * 6.0 + 7.0)


def test_the_legacy_exterior_rule_builds_on_half_the_interior_one(
    symmetric_plate_girder: Section,
) -> None:
    layout = exterior(spacing_ft=7.5, overhang_ft=3.25)
    inner = effective.legacy_interior_width_in(layout, symmetric_plate_girder, 120.0)
    outer = effective.legacy_exterior_width_in(layout, symmetric_plate_girder, 120.0)
    assert outer > inner / 2.0
    assert outer < inner


def test_a_narrow_overhang_governs_the_legacy_exterior_rule(
    symmetric_plate_girder: Section,
) -> None:
    layout = exterior(spacing_ft=7.5, overhang_ft=1.5)
    outer = effective.legacy_exterior_width_in(layout, symmetric_plate_girder, 120.0)
    inner = effective.legacy_interior_width_in(layout, symmetric_plate_girder, 120.0)
    assert outer == pytest.approx(inner / 2.0 + 18.0)


def test_the_legacy_rule_can_beat_the_tributary_rule(symmetric_plate_girder: Section) -> None:
    # A tight girder spacing with a thick deck on a long span: the old slab
    # limit is wider than half the bay, so the newer rule is the tighter one.
    layout = interior(spacing_ft=5.0, slab_in=9.5)
    legacy = effective.width_for(effective.RULE_LEGACY, layout, symmetric_plate_girder, 140.0)
    tributary = effective.width_for(effective.RULE_TRIBUTARY, layout, symmetric_plate_girder, 140.0)
    assert legacy == pytest.approx(tributary)


def test_the_tributary_rule_can_beat_the_legacy_rule(symmetric_plate_girder: Section) -> None:
    layout = interior(spacing_ft=12.0, slab_in=7.0)
    legacy = effective.width_for(effective.RULE_LEGACY, layout, symmetric_plate_girder, 40.0)
    tributary = effective.width_for(effective.RULE_TRIBUTARY, layout, symmetric_plate_girder, 40.0)
    assert tributary > legacy


def test_width_for_dispatches_the_exterior_case(symmetric_plate_girder: Section) -> None:
    layout = exterior()
    assert effective.width_for(
        effective.RULE_LEGACY, layout, symmetric_plate_girder, 100.0
    ) == pytest.approx(effective.legacy_exterior_width_in(layout, symmetric_plate_girder, 100.0))


def test_an_unknown_rule_is_refused_and_lists_the_known_ones(
    symmetric_plate_girder: Section,
) -> None:
    with pytest.raises(GeometryError, match="unknown effective width rule"):
        effective.width_for("tributary2016", interior(), symmetric_plate_girder, 100.0)


def test_a_zero_span_is_refused(symmetric_plate_girder: Section) -> None:
    with pytest.raises(GeometryError, match="not a span"):
        effective.width_for(effective.RULE_LEGACY, interior(), symmetric_plate_girder, 0.0)


def test_a_girder_with_no_neighbour_on_either_side_is_refused() -> None:
    with pytest.raises(GeometryError, match="at least one side"):
        DeckLayout(
            girder_index=0,
            spacing_left_ft=0.0,
            spacing_right_ft=0.0,
            overhang_ft=3.0,
            slab_thickness_in=8.0,
        )


def test_an_exterior_girder_without_an_overhang_is_refused() -> None:
    with pytest.raises(GeometryError, match="needs an overhang"):
        DeckLayout(
            girder_index=0,
            spacing_left_ft=0.0,
            spacing_right_ft=7.5,
            overhang_ft=0.0,
            slab_thickness_in=8.0,
        )


def test_an_interior_girder_carrying_an_overhang_is_refused() -> None:
    with pytest.raises(GeometryError, match="no overhang to carry"):
        DeckLayout(
            girder_index=1,
            spacing_left_ft=7.5,
            spacing_right_ft=7.5,
            overhang_ft=3.0,
            slab_thickness_in=8.0,
        )


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"girder_index": -1}, "zero based"),
        ({"slab_thickness_in": 0.0}, "slab thickness"),
        ({"overhang_ft": -1.0}, "cannot be negative"),
        ({"spacing_right_ft": -7.5}, "cannot be negative"),
    ],
)
def test_a_bad_layout_field_is_refused(kwargs: dict[str, float], message: str) -> None:
    base = {
        "girder_index": 1,
        "spacing_left_ft": 7.5,
        "spacing_right_ft": 7.5,
        "overhang_ft": 0.0,
        "slab_thickness_in": 8.0,
    }
    with pytest.raises(GeometryError, match=message):
        DeckLayout(**{**base, **kwargs})  # type: ignore[arg-type]


def test_the_rule_names_are_the_ones_the_module_exports() -> None:
    assert set(effective.RULES) == {effective.RULE_TRIBUTARY, effective.RULE_LEGACY}
