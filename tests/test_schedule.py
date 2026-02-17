"""The section schedule, and the four ways it refuses to be built wrong."""

from __future__ import annotations

import pytest

from shearstud.errors import GeometryError
from shearstud.geometry.plate import flange, web
from shearstud.geometry.schedule import GirderSchedule, SectionRun, from_breaks, uniform
from shearstud.geometry.section import Section

pytestmark = pytest.mark.geometry


def girder(label: str, bottom_in: float) -> Section:
    return Section(
        label,
        (
            flange("bottom", width_in=16.0, thickness_in=bottom_in, y_center_in=bottom_in / 2.0),
            web("web", thickness_in=0.5, depth_in=54.0, y_center_in=bottom_in + 27.0),
            flange("top", width_in=14.0, thickness_in=1.0, y_center_in=bottom_in + 54.5),
        ),
    )


def three_run_schedule() -> GirderSchedule:
    return from_breaks(
        "G2",
        [girder("end", 1.0), girder("middle", 2.0), girder("far", 1.0)],
        [28.0, 92.0],
        120.0,
    )


def test_a_uniform_schedule_covers_the_whole_girder() -> None:
    s = uniform("G1", girder("only", 1.25), 84.0)
    assert s.is_uniform
    assert s.length_ft == pytest.approx(84.0)
    assert s.transitions_ft == ()


def test_a_uniform_schedule_answers_the_same_section_everywhere() -> None:
    s = uniform("G1", girder("only", 1.25), 84.0)
    assert s.section_at(0.0) is s.section_at(41.7)
    assert s.section_at(41.7) is s.section_at(84.0)


def test_a_three_run_schedule_reports_its_transitions() -> None:
    s = three_run_schedule()
    assert not s.is_uniform
    assert len(s) == 3
    assert s.transitions_ft == pytest.approx((28.0, 92.0))


def test_lookup_lands_in_the_right_run() -> None:
    s = three_run_schedule()
    assert s.section_at(10.0).label == "end"
    assert s.section_at(60.0).label == "middle"
    assert s.section_at(100.0).label == "far"


def test_a_transition_station_belongs_to_the_run_that_starts_there() -> None:
    s = three_run_schedule()
    assert s.section_at(27.9).label == "end"
    assert s.section_at(28.0).label == "middle"


def test_both_ends_of_the_girder_resolve() -> None:
    s = three_run_schedule()
    assert s.section_at(0.0).label == "end"
    assert s.section_at(120.0).label == "far"


def test_a_station_past_the_end_is_an_error_not_a_clamp() -> None:
    s = three_run_schedule()
    with pytest.raises(GeometryError, match="past the end"):
        s.section_at(121.0)


def test_a_station_behind_the_datum_is_an_error_not_a_clamp() -> None:
    s = three_run_schedule()
    with pytest.raises(GeometryError, match="behind the datum"):
        s.section_at(-1.0)


def test_the_sections_come_back_in_station_order() -> None:
    assert [s.label for s in three_run_schedule().sections()] == ["end", "middle", "far"]


def test_run_lengths_add_up_to_the_girder() -> None:
    s = three_run_schedule()
    assert sum(run.length_ft for run in s) == pytest.approx(s.length_ft)


def test_a_run_is_half_open_on_its_far_end() -> None:
    run = SectionRun(10.0, 20.0, girder("r", 1.0))
    assert run.contains(10.0)
    assert run.contains(19.999)
    assert not run.contains(20.0)


def test_a_run_with_no_length_is_refused() -> None:
    with pytest.raises(GeometryError, match="has no length"):
        SectionRun(30.0, 30.0, girder("r", 1.0))


def test_a_backwards_run_is_refused() -> None:
    with pytest.raises(GeometryError, match="has no length"):
        SectionRun(30.0, 12.0, girder("r", 1.0))


def test_a_run_behind_the_datum_is_refused() -> None:
    with pytest.raises(GeometryError, match="behind the datum"):
        SectionRun(-4.0, 12.0, girder("r", 1.0))


def test_a_gap_between_runs_is_refused_and_names_the_station() -> None:
    with pytest.raises(GeometryError, match=r"gap of 5\.000 ft at station 40\.000"):
        GirderSchedule(
            "G3",
            (
                SectionRun(0.0, 40.0, girder("a", 1.0)),
                SectionRun(45.0, 90.0, girder("b", 1.0)),
            ),
        )


def test_an_overlap_between_runs_is_refused_and_says_overlap() -> None:
    with pytest.raises(GeometryError, match="overlap of"):
        GirderSchedule(
            "G3",
            (
                SectionRun(0.0, 40.0, girder("a", 1.0)),
                SectionRun(35.0, 90.0, girder("b", 1.0)),
            ),
        )


def test_a_schedule_that_does_not_start_at_zero_is_refused() -> None:
    with pytest.raises(GeometryError, match="not zero"):
        GirderSchedule("G4", (SectionRun(6.0, 90.0, girder("a", 1.0)),))


def test_an_empty_schedule_is_refused() -> None:
    with pytest.raises(GeometryError, match="at least one run"):
        GirderSchedule("G5", ())


def test_a_schedule_needs_a_label() -> None:
    with pytest.raises(GeometryError, match="needs a label"):
        GirderSchedule(" ", (SectionRun(0.0, 40.0, girder("a", 1.0)),))


def test_from_breaks_counts_the_breaks_it_was_given() -> None:
    with pytest.raises(GeometryError, match="need 2 breaks, got 1"):
        from_breaks("G6", [girder("a", 1.0), girder("b", 1.0), girder("c", 1.0)], [40.0], 120.0)


def test_from_breaks_sorts_the_breaks_it_was_given() -> None:
    out_of_order = from_breaks(
        "G7", [girder("a", 1.0), girder("b", 2.0), girder("c", 1.0)], [92.0, 28.0], 120.0
    )
    assert out_of_order.transitions_ft == pytest.approx((28.0, 92.0))


def test_a_thicker_middle_section_is_stiffer_where_it_matters() -> None:
    s = three_run_schedule()
    assert s.section_at(60.0).inertia_in4 > s.section_at(10.0).inertia_in4


def test_the_run_in_force_is_the_one_the_station_falls_in() -> None:
    s = three_run_schedule()
    assert s.run_at(10.0).section.label == "end"
    assert s.run_at(60.0).section.label == "middle"
    assert s.run_at(100.0).section.label == "far"


def test_a_station_on_a_transition_belongs_to_the_run_that_starts_there() -> None:
    s = three_run_schedule()
    assert s.run_at(28.0).section.label == "middle"
    assert s.run_at(92.0).section.label == "far"


def test_the_run_carries_the_stations_it_covers() -> None:
    run = three_run_schedule().run_at(60.0)
    assert run.from_station_ft == pytest.approx(28.0)
    assert run.to_station_ft == pytest.approx(92.0)


def test_a_station_behind_the_datum_has_no_run() -> None:
    with pytest.raises(GeometryError, match="behind the datum"):
        three_run_schedule().run_at(-5.0)


def test_a_station_past_the_end_has_no_run() -> None:
    with pytest.raises(GeometryError, match="past the end"):
        three_run_schedule().run_at(140.0)


def test_the_ends_of_the_girder_are_inside_the_schedule() -> None:
    s = three_run_schedule()
    assert s.run_at(0.0).section.label == "end"
    assert s.run_at(120.0).section.label == "far"
