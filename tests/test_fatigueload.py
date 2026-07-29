"""The computed stress range, and the four ways the fatigue load is not the
rating load."""

from __future__ import annotations

import pytest

from shearstud.analysis import fatigueload as fl
from shearstud.analysis import ratingrun as rr
from shearstud.analysis.ratingrun import RatingSettings
from shearstud.errors import InputError
from shearstud.geometry.composite import DeckSlab
from shearstud.geometry.effective import DeckLayout
from shearstud.geometry.plate import flange, web
from shearstud.geometry.schedule import uniform
from shearstud.geometry.section import Section
from shearstud.loads import distribution as dist
from shearstud.loads import impact
from shearstud.structure.detail import FIBRE_BOTTOM, FIBRE_TOP, FIBRE_WEB, FatigueDetail
from shearstud.structure.girder import GirderLine
from shearstud.structure.identity import parse
from shearstud.structure.record import Structure
from shearstud.structure.span import simple

pytestmark = pytest.mark.fatigue

SPAN_FT = 90.0


def section() -> Section:
    return Section(
        "PG52",
        (
            flange("bottom", width_in=18.0, thickness_in=1.5, y_center_in=0.75),
            web("web", thickness_in=0.5625, depth_in=52.0, y_center_in=27.5),
            flange("top", width_in=16.0, thickness_in=1.0, y_center_in=54.0),
        ),
    )


def detail(
    detail_id: str = "D1",
    station_ft: float = 24.0,
    fibre: str = FIBRE_BOTTOM,
    kind: str = "cover_plate_end",
    category: str = "E",
) -> FatigueDetail:
    return FatigueDetail(
        detail_id=detail_id,
        kind=kind,
        category_name=category,
        station_ft=station_ft,
        fibre=fibre,
    )


def girder(
    girder_id: str = "G2", index: int = 1, details: tuple[FatigueDetail, ...] = ()
) -> GirderLine:
    return GirderLine(
        girder_id=girder_id,
        schedule=uniform(girder_id, section(), SPAN_FT),
        layout=DeckLayout(
            girder_index=index,
            spacing_left_ft=8.0,
            spacing_right_ft=8.0,
            overhang_ft=0.0,
            slab_thickness_in=8.0,
        ),
        deck=DeckSlab(thickness_in=8.0, effective_width_in=96.0, haunch_in=2.0, fc_ksi=4.0),
        details=details,
    )


def structure(details: tuple[FatigueDetail, ...] = ()) -> Structure:
    return Structure(
        number=parse("18-SH-0473"),
        name="Salt Fork Creek",
        spans=simple(SPAN_FT),
        girders=(
            girder("G1", 0),
            girder("G2", 1, details),
            girder("G3", 2),
            girder("G4", 3),
        ),
        year_built=1968,
    )


def test_the_fatigue_truck_has_the_fixed_rear_spacing() -> None:
    # The rating truck's gap is a parameter at both ends of its range. The
    # fatigue provisions fix it.
    truck = fl.fatigue_truck()
    assert truck.axles[-1].spacing_ft == pytest.approx(fl.FATIGUE_REAR_GAP_FT)


def test_the_fatigue_truck_is_the_design_truck() -> None:
    assert fl.fatigue_truck().name == "HL93-TRUCK"
    assert fl.fatigue_truck().gross_kip == pytest.approx(72.0)


def test_the_distribution_factor_is_one_lane() -> None:
    unit = structure()
    line = unit.girder("G2")
    one_lane = rr.distribution_for(unit, line, RatingSettings(lanes_loaded=1))
    assert fl.distribution_for(unit, line) < one_lane


def test_the_presence_factor_is_taken_back_out() -> None:
    # AASHTO's table factors include it, and for one lane it is 1.2. Leaving
    # it in overstates every computed range by a fifth.
    unit = structure()
    line = unit.girder("G2")
    one_lane = rr.distribution_for(unit, line, RatingSettings(lanes_loaded=1))
    expected = one_lane / dist.presence_factor(1)
    assert fl.distribution_for(unit, line) == pytest.approx(expected)


def test_the_fatigue_factor_is_below_the_rating_one() -> None:
    unit = structure()
    line = unit.girder("G2")
    rating = rr.distribution_for(unit, line, RatingSettings())
    assert fl.distribution_for(unit, line) < rating


def test_the_dynamic_allowance_is_the_fatigue_one() -> None:
    assert impact.allowance_frac(impact.STATE_FATIGUE) == pytest.approx(0.15)
    assert impact.allowance_frac(impact.STATE_FATIGUE) < impact.allowance_frac(
        impact.STATE_STRENGTH
    )


def test_a_bottom_flange_detail_is_taken_at_the_bottom_fibre() -> None:
    assert fl.fibre_of(detail(fibre=FIBRE_BOTTOM)) == FIBRE_BOTTOM


def test_a_top_flange_detail_is_taken_at_the_top_fibre() -> None:
    assert fl.fibre_of(detail(fibre=FIBRE_TOP, kind="groove_weld", category="B")) == FIBRE_TOP


def test_a_web_detail_is_taken_at_the_nearest_flange() -> None:
    # The web details in this inventory are the stiffener terminations at the
    # bottom of the web.
    found = detail(fibre=FIBRE_WEB, kind="stiffener_weld", category="C")
    assert fl.fibre_of(found) == fl.WEB_DETAIL_FIBRE


def test_the_section_modulus_comes_off_the_short_term_section() -> None:
    # Short term at every station. A fatigue load is small enough that the
    # deck stays uncracked, which is the opposite of a strength assumption.
    line = girder()
    composite = line.composite_at(24.0)
    assert fl.section_modulus_for(line, detail()) == pytest.approx(
        composite.short_term.section_modulus_bottom_in3
    )


def test_the_bottom_fibre_modulus_is_the_smaller_one_on_a_composite_section() -> None:
    # The deck puts the neutral axis up near the top flange, so the top steel
    # fibre is the close one and the bottom flange is the far one. That is the
    # opposite of the bare steel section, where the top fibre governs, and it
    # is why the fibre has to be looked up rather than assumed.
    line = girder()
    bottom = fl.section_modulus_for(line, detail())
    top = fl.section_modulus_for(line, detail(fibre=FIBRE_TOP, kind="groove_weld", category="B"))
    assert bottom < top


def test_the_bare_steel_section_puts_the_governing_fibre_at_the_top() -> None:
    steel = section()
    assert steel.section_modulus_top_in3 < steel.section_modulus_bottom_in3


def test_a_stress_range_is_positive_and_modest() -> None:
    unit = structure((detail(),))
    found = fl.stress_range(unit, unit.girder("G2"), detail())
    assert found.range_ksi > 0.0
    # One truck on a ninety foot composite span is a few ksi, not tens.
    assert found.range_ksi < 10.0


def test_a_stress_range_keeps_its_workings() -> None:
    unit = structure((detail(),))
    found = fl.stress_range(unit, unit.girder("G2"), detail())
    assert found.detail_id == "D1"
    assert found.moment_range_kipft > 0.0
    assert found.section_modulus_in3 > 0.0
    assert found.is_computed


def test_the_range_is_the_moment_range_over_the_modulus() -> None:
    unit = structure((detail(),))
    found = fl.stress_range(unit, unit.girder("G2"), detail())
    assert found.range_ksi == pytest.approx(
        found.moment_range_kipft * 12.0 / found.section_modulus_in3
    )


def test_a_detail_at_midspan_sees_more_than_one_near_the_abutment() -> None:
    unit = structure()
    near = fl.stress_range(unit, unit.girder("G2"), detail(station_ft=5.0))
    middle = fl.stress_range(unit, unit.girder("G2"), detail(station_ft=SPAN_FT / 2.0))
    assert middle.range_ksi > near.range_ksi


def test_a_detail_on_the_bottom_flange_sees_more_than_one_on_the_top() -> None:
    # Same moment, smaller modulus, bigger stress. On a composite section the
    # bottom flange is the far fibre, which is also where the cover plate ends
    # are, which is why the worst fatigue detail on these girders is down
    # there.
    unit = structure()
    bottom = fl.stress_range(unit, unit.girder("G2"), detail())
    top = fl.stress_range(
        unit, unit.girder("G2"), detail(fibre=FIBRE_TOP, kind="groove_weld", category="B")
    )
    assert bottom.range_ksi > top.range_ksi


def test_a_detail_past_the_end_of_the_unit_is_refused() -> None:
    unit = structure()
    with pytest.raises(InputError, match="is at 500.0 ft"):
        fl.stress_range(unit, unit.girder("G2"), detail(station_ft=500.0))


def test_every_detail_on_the_structure_gets_a_range() -> None:
    details = (detail("D1"), detail("D2", station_ft=45.0))
    unit = structure(details)
    assert len(fl.ranges_for(unit)) == len(details)


def test_the_ranges_come_back_worst_first() -> None:
    details = (detail("D1", station_ft=5.0), detail("D2", station_ft=45.0))
    ranges = fl.ranges_for(structure(details))
    assert [found.detail_id for found in ranges] == ["D2", "D1"]


def test_a_structure_with_no_details_has_no_ranges() -> None:
    assert fl.ranges_for(structure()) == []


def test_an_exterior_girder_sees_at_least_as_much_as_an_interior_one() -> None:
    unit = structure()
    interior = fl.distribution_for(unit, unit.girder("G2"))
    exterior = fl.distribution_for(unit, unit.girder("G1"))
    assert exterior >= interior
