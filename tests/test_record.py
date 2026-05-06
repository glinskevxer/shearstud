"""The structure aggregate, and the three cross object invariants it holds."""

from __future__ import annotations

from datetime import date

import pytest

from shearstud.errors import InputError
from shearstud.geometry.composite import DeckSlab
from shearstud.geometry.effective import DeckLayout
from shearstud.geometry.plate import flange, web
from shearstud.geometry.schedule import uniform
from shearstud.geometry.section import Section
from shearstud.structure.detail import FIBRE_BOTTOM, FatigueDetail
from shearstud.structure.gauge import ORIENTATION_LONGITUDINAL, GaugeInstall
from shearstud.structure.girder import GirderLine
from shearstud.structure.identity import parse
from shearstud.structure.record import Structure
from shearstud.structure.span import simple

pytestmark = pytest.mark.store

UNIT_FT = 84.0


def section() -> Section:
    return Section(
        "PG48",
        (
            flange("bottom", width_in=16.0, thickness_in=1.25, y_center_in=0.625),
            web("web", thickness_in=0.5, depth_in=48.0, y_center_in=25.25),
            flange("top", width_in=14.0, thickness_in=1.0, y_center_in=49.75),
        ),
    )


def deck() -> DeckSlab:
    return DeckSlab(thickness_in=8.0, effective_width_in=90.0, haunch_in=2.0, fc_ksi=4.0)


def layout(index: int, exterior: bool = False) -> DeckLayout:
    if exterior:
        return DeckLayout(
            girder_index=index,
            spacing_left_ft=0.0,
            spacing_right_ft=7.5,
            overhang_ft=3.0,
            slab_thickness_in=8.0,
        )
    return DeckLayout(
        girder_index=index,
        spacing_left_ft=7.5,
        spacing_right_ft=7.5,
        overhang_ft=0.0,
        slab_thickness_in=8.0,
    )


def detail(detail_id: str, station_ft: float = 20.0) -> FatigueDetail:
    return FatigueDetail(
        detail_id=detail_id,
        kind="cover_plate_end",
        category_name="E",
        station_ft=station_ft,
        fibre=FIBRE_BOTTOM,
    )


def girder(
    girder_id: str, index: int, exterior: bool = False, length_ft: float = UNIT_FT
) -> GirderLine:
    return GirderLine(
        girder_id=girder_id,
        schedule=uniform(girder_id, section(), length_ft),
        layout=layout(index, exterior),
        deck=deck(),
        details=(detail(f"{girder_id}-D1"),),
    )


def gauge(gauge_id: str, detail_id: str, removed: date | None = None) -> GaugeInstall:
    return GaugeInstall(
        gauge_id=gauge_id,
        detail_id=detail_id,
        orientation=ORIENTATION_LONGITUDINAL,
        gauge_factor=2.10,
        installed_on=date(2025, 3, 1),
        channel_limit_ue=1500.0,
        removed_on=removed,
    )


def structure(
    girders: tuple[GirderLine, ...] | None = None,
    gauges: tuple[GaugeInstall, ...] = (),
    year_built: int = 1968,
) -> Structure:
    if girders is None:
        girders = (
            girder("G1", 0, exterior=True),
            girder("G2", 1),
            girder("G3", 2),
            girder("G4", 3, exterior=True),
        )
    return Structure(
        number=parse("18-SH-0473"),
        name="Salt Fork Creek",
        spans=simple(UNIT_FT),
        girders=girders,
        gauges=gauges,
        year_built=year_built,
    )


def test_a_structure_reports_its_shape() -> None:
    s = structure()
    assert s.girder_count == 4
    assert s.length_ft == pytest.approx(UNIT_FT)
    assert str(s.number) == "18-SH-0473"


def test_a_structure_iterates_its_girders() -> None:
    assert [g.girder_id for g in structure()] == ["G1", "G2", "G3", "G4"]


def test_girders_can_be_fetched_by_id() -> None:
    assert structure().girder("G3").layout.girder_index == 2


def test_asking_for_a_girder_that_is_not_there_is_refused() -> None:
    with pytest.raises(InputError, match="no girder 'G9'"):
        structure().girder("G9")


def test_girders_can_be_fetched_by_index() -> None:
    assert structure().girder_at_index(0).girder_id == "G1"


def test_asking_for_an_index_that_is_not_there_is_refused() -> None:
    with pytest.raises(InputError, match="no girder at index 9"):
        structure().girder_at_index(9)


def test_the_exterior_girders_are_the_ones_with_overhangs() -> None:
    assert [g.girder_id for g in structure().exterior_girders()] == ["G1", "G4"]


def test_the_interior_girders_are_the_rest() -> None:
    assert [g.girder_id for g in structure().interior_girders()] == ["G2", "G3"]


def test_every_detail_on_the_structure_comes_back() -> None:
    ids = [d.detail_id for d in structure().details()]
    assert ids == ["G1-D1", "G2-D1", "G3-D1", "G4-D1"]


def test_a_detail_can_be_traced_back_to_its_girder() -> None:
    assert structure().detail_owner("G3-D1").girder_id == "G3"


def test_tracing_a_detail_that_is_not_there_is_refused() -> None:
    with pytest.raises(InputError, match="no detail 'nope'"):
        structure().detail_owner("nope")


def test_a_bare_structure_is_not_instrumented() -> None:
    assert not structure().is_instrumented


def test_a_gauged_structure_is() -> None:
    s = structure(gauges=(gauge("g1", "G3-D1"),))
    assert s.is_instrumented


def test_live_gauges_are_filtered_by_date_and_sorted() -> None:
    s = structure(
        gauges=(
            gauge("b", "G2-D1"),
            gauge("a", "G3-D1"),
            gauge("c", "G4-D1", removed=date(2025, 6, 1)),
        )
    )
    assert [g.gauge_id for g in s.live_gauges(date(2026, 1, 1))] == ["a", "b"]


def test_a_gauge_watching_a_detail_that_is_not_here_is_refused() -> None:
    with pytest.raises(InputError, match="which is not on this structure"):
        structure(gauges=(gauge("g1", "somewhere-else"),))


def test_a_girder_shorter_than_the_unit_is_refused() -> None:
    girders = (
        girder("G1", 0, exterior=True),
        girder("G2", 1, length_ft=60.0),
        girder("G3", 2),
        girder("G4", 3, exterior=True),
    )
    with pytest.raises(InputError, match=r"is 60.0 ft on a 84.0 ft unit"):
        structure(girders=girders)


def test_a_gap_in_the_girder_indices_is_refused() -> None:
    girders = (
        girder("G1", 0, exterior=True),
        girder("G2", 1),
        girder("G4", 3, exterior=True),
    )
    with pytest.raises(InputError, match="not a run from zero"):
        structure(girders=girders)


def test_duplicate_girder_indices_are_refused() -> None:
    girders = (girder("G1", 0, exterior=True), girder("G2", 0, exterior=True))
    with pytest.raises(InputError, match="not a run from zero"):
        structure(girders=girders)


def test_a_structure_with_no_girders_is_refused() -> None:
    with pytest.raises(InputError, match="at least one girder"):
        structure(girders=())


def test_a_structure_needs_a_name() -> None:
    with pytest.raises(InputError, match="needs a name"):
        Structure(
            number=parse("18-SH-0473"),
            name=" ",
            spans=simple(UNIT_FT),
            girders=(girder("G1", 0, exterior=True),),
        )


def test_the_age_is_years_since_it_was_built() -> None:
    assert structure(year_built=1968).age_years(date(2026, 5, 1)) == 58


def test_an_unrecorded_year_built_is_refused() -> None:
    with pytest.raises(InputError, match="year built is not recorded"):
        structure(year_built=0).age_years(date(2026, 5, 1))


def test_gauges_can_be_replaced_wholesale() -> None:
    s = structure()
    fitted = s.with_gauges([gauge("g1", "G2-D1"), gauge("g2", "G3-D1")])
    assert fitted.is_instrumented
    assert not s.is_instrumented
    assert fitted.name == s.name


def test_replacing_gauges_still_checks_the_details_exist() -> None:
    with pytest.raises(InputError, match="not on this structure"):
        structure().with_gauges([gauge("g1", "ghost")])


def test_a_structure_can_swap_its_girders() -> None:
    original = structure()
    swapped = original.with_girders(original.girders[:2])
    assert swapped.girder_count == 2
    assert swapped.number == original.number
    assert swapped.spans is original.spans


def test_swapping_girders_keeps_the_gauges() -> None:
    # Measuring a plate does not move a gauge.
    original = structure()
    swapped = original.with_girders(original.girders)
    assert swapped.gauges == original.gauges
    assert swapped.year_built == original.year_built
    assert swapped.effective_width_rule == original.effective_width_rule
