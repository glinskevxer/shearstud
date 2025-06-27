"""Girder lines: the object every analysis is handed."""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.geometry.composite import DeckSlab
from shearstud.geometry.effective import DeckLayout
from shearstud.geometry.plate import flange, web
from shearstud.geometry.schedule import GirderSchedule, from_breaks, uniform
from shearstud.geometry.section import Section
from shearstud.structure.detail import FIBRE_BOTTOM, FatigueDetail
from shearstud.structure.girder import GirderLine

pytestmark = pytest.mark.store


def plate_section(label: str, bottom_in: float) -> Section:
    return Section(
        label,
        (
            flange("bottom", width_in=16.0, thickness_in=bottom_in, y_center_in=bottom_in / 2.0),
            web("web", thickness_in=0.5, depth_in=48.0, y_center_in=bottom_in + 24.0),
            flange("top", width_in=14.0, thickness_in=1.0, y_center_in=bottom_in + 48.5),
        ),
    )


def schedule() -> GirderSchedule:
    return from_breaks(
        "G3",
        [plate_section("end", 1.0), plate_section("middle", 2.0), plate_section("far", 1.0)],
        [30.0, 90.0],
        120.0,
    )


def interior_layout() -> DeckLayout:
    return DeckLayout(
        girder_index=2,
        spacing_left_ft=7.5,
        spacing_right_ft=7.5,
        overhang_ft=0.0,
        slab_thickness_in=8.0,
    )


def exterior_layout() -> DeckLayout:
    return DeckLayout(
        girder_index=0,
        spacing_left_ft=0.0,
        spacing_right_ft=7.5,
        overhang_ft=3.25,
        slab_thickness_in=8.0,
    )


def deck() -> DeckSlab:
    return DeckSlab(thickness_in=8.0, effective_width_in=90.0, haunch_in=2.0, fc_ksi=4.0)


def detail(
    detail_id: str, station_ft: float, gauges: tuple[str, ...] = (), category: str = "E"
) -> FatigueDetail:
    return FatigueDetail(
        detail_id=detail_id,
        kind="cover_plate_end",
        category_name=category,
        station_ft=station_ft,
        fibre=FIBRE_BOTTOM,
        gauge_ids=gauges,
    )


def girder(details: tuple[FatigueDetail, ...] = ()) -> GirderLine:
    return GirderLine(
        girder_id="18-SH-0473 G3",
        schedule=schedule(),
        layout=interior_layout(),
        deck=deck(),
        details=details,
    )


def test_a_girder_reports_its_length_from_the_schedule() -> None:
    assert girder().length_ft == pytest.approx(120.0)


def test_an_interior_girder_is_not_exterior() -> None:
    assert not girder().is_exterior


def test_an_exterior_girder_says_so() -> None:
    g = GirderLine(girder_id="G1", schedule=schedule(), layout=exterior_layout(), deck=deck())
    assert g.is_exterior


def test_the_section_changes_along_the_girder() -> None:
    g = girder()
    assert g.section_at(10.0).label == "end"
    assert g.section_at(60.0).label == "middle"
    assert g.section_at(110.0).label == "far"


def test_the_composite_girder_at_a_station_uses_that_section() -> None:
    g = girder()
    composite = g.composite_at(60.0)
    assert composite.steel.label == "middle"
    assert composite.short_term.inertia_in4 > composite.noncomposite.inertia_in4


def test_the_composite_girder_gets_stiffer_where_the_flange_is_thicker() -> None:
    g = girder()
    thin = g.composite_at(10.0).short_term.inertia_in4
    thick = g.composite_at(60.0).short_term.inertia_in4
    assert thick > thin


def test_a_girder_with_no_details_iterates_empty() -> None:
    assert list(girder()) == []
    assert girder().gauge_ids() == []


def test_details_can_be_fetched_by_id() -> None:
    g = girder((detail("a", 20.0), detail("b", 40.0)))
    assert g.detail("b").station_ft == pytest.approx(40.0)


def test_asking_for_a_detail_that_is_not_there_is_refused() -> None:
    with pytest.raises(InputError, match="no detail 'z'"):
        girder((detail("a", 20.0),)).detail("z")


def test_details_near_a_station_come_back_within_the_window() -> None:
    g = girder((detail("a", 20.0), detail("b", 24.0), detail("c", 90.0)))
    assert [d.detail_id for d in g.details_near(22.0, 5.0)] == ["a", "b"]


def test_a_window_of_zero_finds_only_an_exact_hit() -> None:
    g = girder((detail("a", 20.0), detail("b", 24.0)))
    assert [d.detail_id for d in g.details_near(24.0, 0.0)] == ["b"]


def test_a_negative_window_is_refused() -> None:
    with pytest.raises(InputError, match="is negative"):
        girder((detail("a", 20.0),)).details_near(20.0, -1.0)


def test_instrumented_details_are_the_ones_with_gauges() -> None:
    g = girder((detail("a", 20.0, ("g1",)), detail("b", 40.0), detail("c", 90.0, ("g2",))))
    assert [d.detail_id for d in g.instrumented_details()] == ["a", "c"]


def test_gauge_ids_are_deduplicated_and_sorted() -> None:
    g = girder(
        (
            detail("a", 20.0, ("g2", "g1")),
            detail("b", 40.0, ("g1",)),
            detail("c", 90.0, ("g3",)),
        )
    )
    assert g.gauge_ids() == ["g1", "g2", "g3"]


def test_a_detail_past_the_end_of_the_girder_is_refused() -> None:
    with pytest.raises(InputError, match="past the end at 120.0"):
        girder((detail("a", 300.0),))


def test_a_detail_exactly_at_the_far_end_is_allowed() -> None:
    assert girder((detail("a", 120.0),)).detail("a").station_ft == pytest.approx(120.0)


def test_two_details_sharing_an_id_are_refused() -> None:
    with pytest.raises(InputError, match="share an id"):
        girder((detail("a", 20.0), detail("a", 40.0)))


def test_details_out_of_station_order_are_refused() -> None:
    with pytest.raises(InputError, match="not in station order"):
        girder((detail("far", 90.0), detail("near", 20.0)))


def test_a_girder_needs_an_id() -> None:
    with pytest.raises(InputError, match="needs an id"):
        GirderLine(girder_id="  ", schedule=schedule(), layout=interior_layout(), deck=deck())


def test_replacing_the_details_sorts_them() -> None:
    g = girder().with_details([detail("far", 90.0), detail("near", 20.0)])
    assert [d.detail_id for d in g] == ["near", "far"]


def test_adding_a_detail_keeps_the_order() -> None:
    g = girder((detail("a", 20.0), detail("c", 90.0)))
    grown = g.add_detail(detail("b", 50.0))
    assert [d.detail_id for d in grown] == ["a", "b", "c"]


def test_adding_a_detail_leaves_the_original_alone() -> None:
    g = girder((detail("a", 20.0),))
    g.add_detail(detail("b", 50.0))
    assert [d.detail_id for d in g] == ["a"]


def test_a_uniform_schedule_works_just_as_well() -> None:
    g = GirderLine(
        girder_id="G9",
        schedule=uniform("G9", plate_section("only", 1.25), 62.0),
        layout=interior_layout(),
        deck=deck(),
    )
    assert g.length_ft == pytest.approx(62.0)
    assert g.section_at(0.0) is g.section_at(62.0)
