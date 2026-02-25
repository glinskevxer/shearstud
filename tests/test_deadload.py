"""Dead load, and which composite stage each part lands on."""

from __future__ import annotations

import pytest

from shearstud.analysis import deadload as dl
from shearstud.errors import InputError
from shearstud.geometry.composite import DeckSlab
from shearstud.geometry.effective import DeckLayout
from shearstud.geometry.plate import flange, web
from shearstud.geometry.schedule import uniform
from shearstud.geometry.section import Section
from shearstud.structure.girder import GirderLine

pytestmark = pytest.mark.loads

SPAN_FT = 90.0


def girder(area_scale: float = 1.0) -> GirderLine:
    section = Section(
        "PG48",
        (
            flange("bottom", width_in=16.0 * area_scale, thickness_in=1.25, y_center_in=0.625),
            web("web", thickness_in=0.5, depth_in=48.0, y_center_in=25.25),
            flange("top", width_in=14.0, thickness_in=1.0, y_center_in=49.75),
        ),
    )
    return GirderLine(
        girder_id="G3",
        schedule=uniform("G3", section, SPAN_FT),
        layout=DeckLayout(
            girder_index=1,
            spacing_left_ft=7.5,
            spacing_right_ft=7.5,
            overhang_ft=0.0,
            slab_thickness_in=8.0,
        ),
        deck=DeckSlab(thickness_in=8.0, effective_width_in=90.0, haunch_in=2.0, fc_ksi=4.0),
    )


def test_the_steel_weight_is_the_area_times_the_density() -> None:
    g = girder()
    area_in2 = g.section_at(0.0).area_in2
    bare = area_in2 / 144.0 * 0.490
    assert dl.steel_weight_klf(g, 0.0) == pytest.approx(bare * 1.08)


def test_a_heavier_girder_weighs_more() -> None:
    assert dl.steel_weight_klf(girder(2.0), 0.0) > dl.steel_weight_klf(girder(1.0), 0.0)


def test_a_plate_girder_weighs_a_few_hundred_pounds_a_foot() -> None:
    got = dl.steel_weight_klf(girder(), 0.0)
    assert 0.15 < got < 0.40


def test_the_deck_weight_includes_the_haunch() -> None:
    g = girder()
    slab_only = 8.0 * 90.0 / 144.0 * 0.150
    assert dl.deck_weight_klf(g) > slab_only


def test_the_deck_is_the_heaviest_dead_load_on_a_girder() -> None:
    g = girder()
    assert dl.deck_weight_klf(g) > dl.steel_weight_klf(g, 0.0)


def test_an_exterior_girder_can_keep_the_whole_barrier() -> None:
    assert dl.barrier_weight_klf(0.45, 4, 1.0) == pytest.approx(0.45)


def test_spreading_the_barrier_leaves_nothing_on_the_exterior_girder() -> None:
    assert dl.barrier_weight_klf(0.45, 4, 0.0) == pytest.approx(0.0)


def test_a_share_outside_the_range_is_refused() -> None:
    with pytest.raises(InputError, match="outside zero to one"):
        dl.barrier_weight_klf(0.45, 4, 1.5)


def test_a_cross_section_with_no_girders_is_refused() -> None:
    with pytest.raises(InputError, match="not a cross section"):
        dl.barrier_weight_klf(0.45, 0, 1.0)


def test_a_negative_barrier_is_refused() -> None:
    with pytest.raises(InputError, match="is negative"):
        dl.barrier_weight_klf(-0.45, 4, 1.0)


def test_a_three_inch_overlay_over_seven_and_a_half_feet() -> None:
    assert dl.wearing_surface_klf(3.0, 7.5) == pytest.approx(0.25 * 7.5 * 0.140)


def test_a_thicker_overlay_weighs_more() -> None:
    assert dl.wearing_surface_klf(4.0, 7.5) > dl.wearing_surface_klf(2.0, 7.5)


def test_no_overlay_weighs_nothing() -> None:
    assert dl.wearing_surface_klf(0.0, 7.5) == pytest.approx(0.0)


def test_a_negative_overlay_is_refused() -> None:
    with pytest.raises(InputError, match="is negative"):
        dl.wearing_surface_klf(-1.0, 7.5)


def test_a_tributary_width_of_zero_is_refused() -> None:
    with pytest.raises(InputError, match="is not a width"):
        dl.wearing_surface_klf(3.0, 0.0)


def test_a_bare_girder_has_two_dead_load_parts() -> None:
    parts = dl.parts_for(girder(), 0.0)
    assert [p.name for p in parts] == ["girder", "deck"]
    assert all(p.stage == dl.STAGE_NONCOMPOSITE for p in parts)


def test_the_barrier_and_the_overlay_land_on_the_composite_section() -> None:
    parts = dl.parts_for(girder(), 0.0, barrier_klf=0.45, overlay_in=3.0, exterior_share_frac=1.0)
    later = [p for p in parts if p.stage == dl.STAGE_LONG_TERM]
    assert [p.name for p in later] == ["barrier", "wearing surface"]


def test_only_the_overlay_is_flagged_as_a_wearing_surface() -> None:
    parts = dl.parts_for(girder(), 0.0, barrier_klf=0.45, overlay_in=3.0, exterior_share_frac=1.0)
    flagged = [p.name for p in parts if p.is_wearing_surface]
    assert flagged == ["wearing surface"]


def test_a_barrier_of_zero_does_not_appear_at_all() -> None:
    parts = dl.parts_for(girder(), 0.0, barrier_klf=0.0, overlay_in=3.0)
    assert "barrier" not in [p.name for p in parts]


def test_the_total_adds_up_every_part() -> None:
    parts = dl.parts_for(girder(), 0.0, barrier_klf=0.45, overlay_in=3.0, exterior_share_frac=1.0)
    assert dl.total_klf(parts) == pytest.approx(sum(p.load_klf for p in parts))


def test_the_total_can_be_taken_for_one_stage() -> None:
    parts = dl.parts_for(girder(), 0.0, barrier_klf=0.45, overlay_in=3.0, exterior_share_frac=1.0)
    early = dl.total_klf(parts, dl.STAGE_NONCOMPOSITE)
    late = dl.total_klf(parts, dl.STAGE_LONG_TERM)
    assert early + late == pytest.approx(dl.total_klf(parts))
    assert early > late


def test_an_unknown_stage_is_refused_by_the_total() -> None:
    with pytest.raises(InputError, match="unknown load stage"):
        dl.total_klf(dl.parts_for(girder(), 0.0), "short_term")


def test_the_factor_split_puts_the_overlay_on_its_own() -> None:
    parts = dl.parts_for(girder(), 0.0, barrier_klf=0.45, overlay_in=3.0, exterior_share_frac=1.0)
    component, surface = dl.component_and_surface_klf(parts)
    assert surface == pytest.approx(dl.wearing_surface_klf(3.0, 7.5))
    assert component + surface == pytest.approx(dl.total_klf(parts))


def test_a_girder_with_no_overlay_has_no_surface_load() -> None:
    component, surface = dl.component_and_surface_klf(dl.parts_for(girder(), 0.0))
    assert surface == pytest.approx(0.0)
    assert component > 0.0


def test_a_part_needs_a_name() -> None:
    with pytest.raises(InputError, match="needs a name"):
        dl.DeadLoadPart(" ", 1.0, dl.STAGE_NONCOMPOSITE)


def test_a_negative_part_is_refused() -> None:
    with pytest.raises(InputError, match="negative load"):
        dl.DeadLoadPart("girder", -1.0, dl.STAGE_NONCOMPOSITE)


def test_a_part_on_an_unknown_stage_is_refused() -> None:
    with pytest.raises(InputError, match="unknown load stage"):
        dl.DeadLoadPart("girder", 1.0, "short_term")


def test_the_midspan_moment_is_wl_squared_over_eight() -> None:
    assert dl.simple_span_moment_kipft(1.2, 90.0) == pytest.approx(1.2 * 8100.0 / 8.0)


def test_the_end_shear_is_wl_over_two() -> None:
    assert dl.simple_span_shear_kip(1.2, 90.0) == pytest.approx(54.0)


@pytest.mark.parametrize("fn", [dl.simple_span_moment_kipft, dl.simple_span_shear_kip])
def test_a_span_of_zero_is_refused(fn: object) -> None:
    with pytest.raises(InputError, match="is not a span"):
        fn(1.2, 0.0)  # type: ignore[operator]
