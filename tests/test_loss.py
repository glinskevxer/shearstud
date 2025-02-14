"""Section loss: the two decisions this module makes are both asserted."""

from __future__ import annotations

from datetime import date

import pytest

from shearstud.errors import GeometryError, RecordError
from shearstud.geometry import loss
from shearstud.geometry.loss import ThicknessReading
from shearstud.geometry.section import Section

pytestmark = pytest.mark.geometry

WHEN = date(2025, 4, 18)


def reading(label: str, remaining_in: float, station_ft: float = 20.0) -> ThicknessReading:
    return ThicknessReading(
        plate_label=label,
        station_ft=station_ft,
        remaining_in=remaining_in,
        measured_on=WHEN,
    )


def test_nominal_thickness_is_the_thin_dimension(symmetric_plate_girder: Section) -> None:
    assert loss.nominal_thickness_in(symmetric_plate_girder, "bottom") == pytest.approx(1.0)
    assert loss.nominal_thickness_in(symmetric_plate_girder, "web") == pytest.approx(0.5)


def test_one_reading_gives_one_loss(symmetric_plate_girder: Section) -> None:
    worst = loss.worst_loss_by_plate(symmetric_plate_girder, [reading("bottom", 0.85)])
    assert worst == {"bottom": pytest.approx(0.15)}


def test_the_worst_reading_wins_not_the_average(symmetric_plate_girder: Section) -> None:
    readings = [
        reading("bottom", 0.98, station_ft=5.0),
        reading("bottom", 0.72, station_ft=30.0),
        reading("bottom", 0.95, station_ft=55.0),
    ]
    worst = loss.worst_loss_by_plate(symmetric_plate_girder, readings)
    assert worst["bottom"] == pytest.approx(0.28)


def test_a_reading_thicker_than_nominal_is_not_a_gain(symmetric_plate_girder: Section) -> None:
    worst = loss.worst_loss_by_plate(symmetric_plate_girder, [reading("bottom", 1.04)])
    assert worst["bottom"] == 0.0


def test_a_surplus_reading_does_not_hide_a_real_one(symmetric_plate_girder: Section) -> None:
    readings = [reading("bottom", 1.04), reading("bottom", 0.80)]
    worst = loss.worst_loss_by_plate(symmetric_plate_girder, readings)
    assert worst["bottom"] == pytest.approx(0.20)


def test_loss_under_the_noise_floor_is_dropped(symmetric_plate_girder: Section) -> None:
    worst = loss.worst_loss_by_plate(symmetric_plate_girder, [reading("bottom", 0.997)])
    assert worst["bottom"] == 0.0


def test_loss_just_over_the_noise_floor_is_kept(symmetric_plate_girder: Section) -> None:
    worst = loss.worst_loss_by_plate(symmetric_plate_girder, [reading("bottom", 0.99)])
    assert worst["bottom"] == pytest.approx(0.01)


def test_an_unmeasured_plate_is_absent_not_zero(symmetric_plate_girder: Section) -> None:
    worst = loss.worst_loss_by_plate(symmetric_plate_girder, [reading("bottom", 0.85)])
    assert "web" not in worst
    assert "top" not in worst


def test_applying_loss_thins_only_the_named_plate(symmetric_plate_girder: Section) -> None:
    reduced = loss.apply_loss(symmetric_plate_girder, {"bottom": 0.25})
    assert reduced.plate("bottom").height_in == pytest.approx(0.75)
    assert reduced.plate("web").width_in == pytest.approx(0.5)
    assert reduced.plate("top").height_in == pytest.approx(1.0)


def test_applying_loss_leaves_the_plates_where_they_were(symmetric_plate_girder: Section) -> None:
    reduced = loss.apply_loss(symmetric_plate_girder, {"bottom": 0.25})
    for label in ("bottom", "web", "top"):
        original = symmetric_plate_girder.plate(label)
        assert reduced.plate(label).y_center_in == pytest.approx(original.y_center_in)


def test_losing_the_bottom_flange_raises_the_neutral_axis(
    symmetric_plate_girder: Section,
) -> None:
    reduced = loss.apply_loss(symmetric_plate_girder, {"bottom": 0.4})
    assert reduced.centroid_in > symmetric_plate_girder.centroid_in


def test_losing_the_bottom_flange_costs_bottom_fibre_capacity(
    symmetric_plate_girder: Section,
) -> None:
    before = symmetric_plate_girder.section_modulus_bottom_in3
    after = loss.apply_loss(symmetric_plate_girder, {"bottom": 0.4}).section_modulus_bottom_in3
    assert after < before


def test_naming_a_plate_that_is_not_there_is_refused(symmetric_plate_girder: Section) -> None:
    with pytest.raises(GeometryError, match="cover"):
        loss.apply_loss(symmetric_plate_girder, {"cover": 0.1})


def test_the_measured_section_is_the_two_steps_together(
    symmetric_plate_girder: Section,
) -> None:
    readings = [reading("bottom", 0.70), reading("web", 0.40)]
    direct = loss.measured_section(symmetric_plate_girder, readings)
    staged = loss.apply_loss(symmetric_plate_girder, {"bottom": 0.30, "web": 0.10})
    assert direct.inertia_in4 == pytest.approx(staged.inertia_in4)


def test_a_reading_with_no_steel_left_is_refused() -> None:
    with pytest.raises(RecordError, match="not a thickness"):
        reading("bottom", 0.0)


def test_a_reading_needs_a_plate_label() -> None:
    with pytest.raises(RecordError, match="needs a plate label"):
        ThicknessReading(plate_label=" ", station_ft=1.0, remaining_in=0.5, measured_on=WHEN)


def test_a_station_behind_the_datum_is_refused() -> None:
    with pytest.raises(RecordError, match="behind the datum"):
        reading("bottom", 0.9, station_ft=-2.0)


def test_a_reading_that_removes_the_whole_plate_is_refused(
    symmetric_plate_girder: Section,
) -> None:
    with pytest.raises(GeometryError, match="removes the whole plate"):
        loss.measured_section(symmetric_plate_girder, [reading("web", 0.0001)])


def test_a_finding_reports_the_fractions_it_was_built_from() -> None:
    f = loss.LossFinding(plate_label="bottom", nominal_in=1.0, loss_in=0.2)
    assert f.loss_frac == pytest.approx(0.2)
    assert f.remaining_frac == pytest.approx(0.8)


def test_a_small_loss_is_not_a_finding() -> None:
    f = loss.LossFinding(plate_label="bottom", nominal_in=1.0, loss_in=0.05)
    assert not f.is_finding
    assert not f.is_severe


def test_a_tenth_of_the_plate_is_a_finding() -> None:
    f = loss.LossFinding(plate_label="bottom", nominal_in=1.0, loss_in=0.10)
    assert f.is_finding
    assert not f.is_severe


def test_a_quarter_of_the_plate_is_severe() -> None:
    f = loss.LossFinding(plate_label="web", nominal_in=0.5, loss_in=0.125)
    assert f.is_finding
    assert f.is_severe


def test_findings_come_back_worst_first(symmetric_plate_girder: Section) -> None:
    readings = [reading("bottom", 0.95), reading("web", 0.30), reading("top", 0.85)]
    out = loss.findings(symmetric_plate_girder, readings)
    assert [f.plate_label for f in out] == ["web", "top", "bottom"]
    assert out[0].loss_frac > out[-1].loss_frac


def test_findings_cover_only_the_plates_that_were_measured(
    symmetric_plate_girder: Section,
) -> None:
    out = loss.findings(symmetric_plate_girder, [reading("web", 0.45)])
    assert [f.plate_label for f in out] == ["web"]


def test_a_sound_section_keeps_all_of_its_capacity(symmetric_plate_girder: Section) -> None:
    frac = loss.remaining_capacity_frac(symmetric_plate_girder, [reading("bottom", 1.0)])
    assert frac == pytest.approx(1.0)


def test_a_corroded_bottom_flange_costs_measurable_capacity(
    symmetric_plate_girder: Section,
) -> None:
    frac = loss.remaining_capacity_frac(symmetric_plate_girder, [reading("bottom", 0.70)])
    assert 0.80 < frac < 0.95


def test_the_thresholds_are_ordered() -> None:
    assert 0.0 < loss.FINDING_THRESHOLD_FRAC < loss.SEVERE_THRESHOLD_FRAC < 1.0
