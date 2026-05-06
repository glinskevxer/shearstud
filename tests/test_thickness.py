"""Thickness readings, and the rule that stops two of them stacking up."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from shearstud.errors import StorageError
from shearstud.geometry.composite import DeckSlab
from shearstud.geometry.effective import DeckLayout
from shearstud.geometry.plate import flange, web
from shearstud.geometry.schedule import from_breaks, uniform
from shearstud.geometry.section import Section
from shearstud.store import db, inventory
from shearstud.store import thickness as th
from shearstud.store.thickness import StoredReading
from shearstud.structure.girder import GirderLine
from shearstud.structure.identity import parse
from shearstud.structure.record import Structure
from shearstud.structure.span import simple

pytestmark = pytest.mark.store

NUMBER = "18-SH-0473"
GIRDER = "G3"


def section() -> Section:
    return Section(
        "G3",
        (
            flange("bottom", width_in=18.0, thickness_in=1.5, y_center_in=0.75),
            web("web", thickness_in=0.5, depth_in=52.0, y_center_in=27.5),
            flange("top", width_in=16.0, thickness_in=1.0, y_center_in=54.0),
        ),
    )


def reading(
    plate: str = "bottom",
    station_ft: float = 24.5,
    remaining_in: float = 1.35,
    when: date = date(2026, 4, 2),
    note: str = "",
    girder_id: str = GIRDER,
) -> StoredReading:
    return StoredReading(
        structure_number=NUMBER,
        girder_id=girder_id,
        plate_label=plate,
        station_ft=station_ft,
        remaining_in=remaining_in,
        measured_on=when,
        note=note,
    )


def test_a_reading_round_trips(seeded_book: Path) -> None:
    th.save(seeded_book, reading(note="under the leaking joint"))
    found = th.load(seeded_book, NUMBER)
    assert len(found) == 1
    assert found[0].plate_label == "bottom"
    assert found[0].remaining_in == pytest.approx(1.35)
    assert found[0].note == "under the leaking joint"


def test_readings_come_back_newest_first(seeded_book: Path) -> None:
    th.save(seeded_book, reading(when=date(2019, 4, 2), remaining_in=1.46))
    th.save(seeded_book, reading(when=date(2026, 4, 2), remaining_in=1.35))
    assert [r.measured_on for r in th.load(seeded_book, NUMBER)] == [
        date(2026, 4, 2),
        date(2019, 4, 2),
    ]


def test_the_same_place_on_the_same_day_is_one_reading(seeded_book: Path) -> None:
    th.save(seeded_book, reading(remaining_in=1.35))
    th.save(seeded_book, reading(remaining_in=1.31, note="probe was on a pit"))
    assert db.row_count(seeded_book, "thickness_readings") == 1
    assert th.load(seeded_book, NUMBER)[0].remaining_in == pytest.approx(1.31)
    assert th.load(seeded_book, NUMBER)[0].note == "probe was on a pit"


def test_the_same_place_years_later_is_a_second_reading(seeded_book: Path) -> None:
    th.save(seeded_book, reading(when=date(2019, 4, 2), remaining_in=1.46))
    th.save(seeded_book, reading(when=date(2026, 4, 2), remaining_in=1.35))
    assert db.row_count(seeded_book, "thickness_readings") == 2


def test_readings_can_be_narrowed_to_one_girder(seeded_book: Path) -> None:
    db.execute(
        seeded_book,
        "INSERT INTO girders (structure_number, girder_id, girder_index, spacing_left_ft, "
        "spacing_right_ft, overhang_ft, slab_thickness_in, haunch_in, deck_fc_ksi) "
        "VALUES (?, 'G4', 1, 7.5, 7.5, 0.0, 8.0, 2.0, 4.0)",
        (NUMBER,),
    )
    th.save(seeded_book, reading())
    th.save(seeded_book, reading(girder_id="G4"))
    assert len(th.load(seeded_book, NUMBER)) == 2
    assert len(th.load(seeded_book, NUMBER, GIRDER)) == 1


def test_a_reading_on_a_girder_that_is_not_there_is_refused(seeded_book: Path) -> None:
    with pytest.raises(Exception, match="FOREIGN KEY"):
        th.save(seeded_book, reading(girder_id="G9"))


def test_readings_go_when_the_structure_does(seeded_book: Path) -> None:
    th.save(seeded_book, reading())
    db.execute(seeded_book, "DELETE FROM structures WHERE number = ?", (NUMBER,))
    assert db.row_count(seeded_book, "thickness_readings") == 0


def test_the_newest_reading_at_a_place_is_the_one_that_counts() -> None:
    old = reading(when=date(2019, 4, 2), remaining_in=1.46)
    new = reading(when=date(2026, 4, 2), remaining_in=1.35)
    assert th.newest_per_location([old, new]) == [new]


def test_two_places_on_one_plate_are_two_locations() -> None:
    near = reading(station_ft=24.5)
    far = reading(station_ft=60.0)
    assert len(th.newest_per_location([near, far])) == 2


def test_a_station_written_down_slightly_differently_is_the_same_place() -> None:
    # A field sheet records to the nearest half foot, and the same weld gets
    # written as 24.5 one year and 24.0 the next.
    first = reading(station_ft=24.5, when=date(2019, 4, 2), remaining_in=1.46)
    second = reading(station_ft=24.0, when=date(2026, 4, 2), remaining_in=1.35)
    assert th.newest_per_location([first, second]) == [second]


def test_the_same_station_on_two_plates_is_two_locations() -> None:
    bottom = reading(plate="bottom")
    webbing = reading(plate="web", remaining_in=0.44)
    assert len(th.newest_per_location([bottom, webbing])) == 2


def test_the_locations_come_back_in_a_settled_order() -> None:
    far = reading(station_ft=60.0)
    near = reading(station_ft=10.0)
    ordered = th.newest_per_location([far, near])
    assert [r.station_ft for r in ordered] == [10.0, 60.0]


def test_a_structure_with_no_readings_keeps_its_nominal_section(seeded_book: Path) -> None:
    nominal = section()
    assert th.measured(seeded_book, NUMBER, GIRDER, nominal) is nominal


def test_a_reading_reduces_the_section(seeded_book: Path) -> None:
    th.save(seeded_book, reading(remaining_in=1.20))
    reduced = th.measured(seeded_book, NUMBER, GIRDER, section())
    assert reduced.plate("bottom").height_in == pytest.approx(1.20)
    assert reduced.section_modulus_bottom_in3 < section().section_modulus_bottom_in3


def test_an_old_reading_does_not_stack_on_a_new_one(seeded_book: Path) -> None:
    # Applying both would take 0.15 off and then another 0.04, and come out
    # thinner than anybody has ever measured.
    th.save(seeded_book, reading(when=date(2019, 4, 2), remaining_in=1.46))
    th.save(seeded_book, reading(when=date(2026, 4, 2), remaining_in=1.35))
    reduced = th.measured(seeded_book, NUMBER, GIRDER, section())
    assert reduced.plate("bottom").height_in == pytest.approx(1.35)


def test_the_worst_of_two_places_governs_the_plate(seeded_book: Path) -> None:
    th.save(seeded_book, reading(station_ft=10.0, remaining_in=1.45))
    th.save(seeded_book, reading(station_ft=60.0, remaining_in=1.20))
    reduced = th.measured(seeded_book, NUMBER, GIRDER, section())
    assert reduced.plate("bottom").height_in == pytest.approx(1.20)


def test_a_reading_thicker_than_nominal_takes_nothing_off(seeded_book: Path) -> None:
    th.save(seeded_book, reading(remaining_in=1.60))
    reduced = th.measured(seeded_book, NUMBER, GIRDER, section())
    assert reduced.plate("bottom").height_in == pytest.approx(1.5)


def test_a_book_with_no_readings_says_so(seeded_book: Path) -> None:
    assert not th.has_readings(seeded_book, NUMBER)
    th.save(seeded_book, reading())
    assert th.has_readings(seeded_book, NUMBER)
    assert th.has_readings(seeded_book, NUMBER, GIRDER)


def test_the_days_somebody_measured_come_back_newest_first(seeded_book: Path) -> None:
    th.save(seeded_book, reading(when=date(2019, 4, 2)))
    th.save(seeded_book, reading(when=date(2026, 4, 2)))
    th.save(seeded_book, reading(station_ft=60.0, when=date(2026, 4, 2)))
    assert th.measured_on_dates(seeded_book, NUMBER) == [date(2026, 4, 2), date(2019, 4, 2)]


def test_two_readings_seven_years_apart_give_a_rate() -> None:
    old = reading(when=date(2019, 4, 2), remaining_in=1.46)
    new = reading(when=date(2026, 4, 2), remaining_in=1.32)
    rate = th.corrosion_rate_in_per_yr([old, new])
    assert rate is not None
    assert rate == pytest.approx(0.14 / 7.0, rel=0.01)


def test_one_reading_gives_no_rate() -> None:
    # A single reading says how thin the plate is and nothing about how fast
    # it got that way. That is not an error, it is the usual case.
    assert th.corrosion_rate_in_per_yr([reading()]) is None
    assert th.corrosion_rate_in_per_yr([]) is None


def test_two_readings_on_one_day_give_no_rate() -> None:
    first = reading(remaining_in=1.40)
    second = reading(station_ft=60.0, remaining_in=1.30)
    assert th.corrosion_rate_in_per_yr([first, second]) is None


def test_a_plate_that_is_getting_thicker_gives_a_negative_rate() -> None:
    # Which means somebody mis-measured, and a negative number says so more
    # usefully than clamping it at zero would.
    old = reading(when=date(2019, 4, 2), remaining_in=1.32)
    new = reading(when=date(2026, 4, 2), remaining_in=1.46)
    rate = th.corrosion_rate_in_per_yr([old, new])
    assert rate is not None
    assert rate < 0.0


def test_readings_can_be_forgotten(seeded_book: Path) -> None:
    th.save(seeded_book, reading())
    th.save(seeded_book, reading(station_ft=60.0))
    assert th.delete(seeded_book, NUMBER) == 2
    assert th.load(seeded_book, NUMBER) == []


def test_forgetting_a_structure_with_no_readings_is_quiet(seeded_book: Path) -> None:
    assert th.delete(seeded_book, NUMBER) == 0


def test_a_reading_with_no_structure_number_is_refused() -> None:
    with pytest.raises(StorageError, match="needs a structure number"):
        StoredReading(
            structure_number="  ",
            girder_id=GIRDER,
            plate_label="bottom",
            station_ft=24.5,
            remaining_in=1.35,
            measured_on=date(2026, 4, 2),
        )


def test_a_reading_with_no_girder_is_refused() -> None:
    with pytest.raises(StorageError, match="needs a girder"):
        reading(girder_id="  ")


def test_a_reading_with_no_plate_is_refused() -> None:
    with pytest.raises(StorageError, match="needs a plate label"):
        reading(plate="  ")


def test_a_thickness_of_zero_is_refused() -> None:
    with pytest.raises(StorageError, match="is not a thickness"):
        reading(remaining_in=0.0)


def test_a_station_behind_the_datum_is_refused() -> None:
    with pytest.raises(StorageError, match="behind the datum"):
        reading(station_ft=-1.0)


def test_a_stored_reading_becomes_a_geometry_reading() -> None:
    found = reading().as_reading()
    assert found.plate_label == "bottom"
    assert found.remaining_in == pytest.approx(1.35)


def test_two_readings_within_the_tolerance_are_near_each_other() -> None:
    assert reading(station_ft=24.5).is_near(reading(station_ft=24.9))
    assert not reading(station_ft=24.5).is_near(reading(station_ft=26.0))


def test_two_readings_on_different_plates_are_never_near_each_other() -> None:
    assert not reading(plate="bottom", station_ft=24.5).is_near(
        reading(plate="web", station_ft=24.5)
    )


def test_readings_a_tenth_of_a_foot_apart_are_one_location() -> None:
    # A bucket would put these on either side of a boundary and call them two
    # places, which is the failure the grouping is written to avoid.
    groups = th.locations([reading(station_ft=24.45), reading(station_ft=24.55)])
    assert len(groups) == 1


def test_readings_along_a_patch_of_rust_chain_into_one_location() -> None:
    stations = [24.0, 24.9, 25.8]
    groups = th.locations([reading(station_ft=at) for at in stations])
    assert len(groups) == 1
    assert [r.station_ft for r in groups[0]] == stations


def test_a_gap_wider_than_the_tolerance_starts_a_new_location() -> None:
    groups = th.locations([reading(station_ft=24.0), reading(station_ft=60.0)])
    assert len(groups) == 2


def test_grouping_nothing_gives_nothing() -> None:
    assert th.locations([]) == []


def three_run_girder() -> GirderLine:
    """A girder with a light section at each end and a heavy one in the middle."""
    return GirderLine(
        girder_id=GIRDER,
        schedule=from_breaks(
            GIRDER,
            [section(), heavy_section(), section()],
            [30.0, 90.0],
            120.0,
        ),
        layout=DeckLayout(
            girder_index=0,
            spacing_left_ft=7.5,
            spacing_right_ft=7.5,
            overhang_ft=0.0,
            slab_thickness_in=8.0,
        ),
        deck=DeckSlab(thickness_in=8.0, effective_width_in=90.0, haunch_in=2.0, fc_ksi=4.0),
    )


def heavy_section() -> Section:
    return Section(
        "G3-heavy",
        (
            flange("bottom", width_in=18.0, thickness_in=2.5, y_center_in=1.25),
            web("web", thickness_in=0.5, depth_in=52.0, y_center_in=28.0),
            flange("top", width_in=16.0, thickness_in=1.0, y_center_in=54.5),
        ),
    )


def test_a_girder_with_no_readings_comes_back_unchanged(seeded_book: Path) -> None:
    girder = three_run_girder()
    assert th.measured_girder(seeded_book, NUMBER, girder) is girder


def test_a_reading_reduces_the_run_it_sits_on(seeded_book: Path) -> None:
    th.save(seeded_book, reading(station_ft=10.0, remaining_in=1.20))
    reduced = th.measured_girder(seeded_book, NUMBER, three_run_girder())
    assert reduced.section_at(10.0).plate("bottom").height_in == pytest.approx(1.20)


def test_a_reading_leaves_the_other_runs_alone(seeded_book: Path) -> None:
    # The corrosion is under the leaking joint at one end. Applying its loss to
    # the heavy section over the pier would take a sixteenth off a plate nobody
    # has measured.
    th.save(seeded_book, reading(station_ft=10.0, remaining_in=1.20))
    reduced = th.measured_girder(seeded_book, NUMBER, three_run_girder())
    assert reduced.section_at(60.0).plate("bottom").height_in == pytest.approx(2.5)
    assert reduced.section_at(110.0).plate("bottom").height_in == pytest.approx(1.5)


def test_each_run_takes_its_own_worst_reading(seeded_book: Path) -> None:
    th.save(seeded_book, reading(station_ft=10.0, remaining_in=1.30))
    th.save(seeded_book, reading(station_ft=110.0, remaining_in=1.10))
    reduced = th.measured_girder(seeded_book, NUMBER, three_run_girder())
    assert reduced.section_at(10.0).plate("bottom").height_in == pytest.approx(1.30)
    assert reduced.section_at(110.0).plate("bottom").height_in == pytest.approx(1.10)


def test_the_reduced_girder_keeps_its_length(seeded_book: Path) -> None:
    th.save(seeded_book, reading(station_ft=10.0, remaining_in=1.20))
    reduced = th.measured_girder(seeded_book, NUMBER, three_run_girder())
    assert reduced.length_ft == pytest.approx(120.0)
    assert len(reduced.schedule) == 3


def test_the_reduced_girder_keeps_its_details(seeded_book: Path) -> None:
    # A reduced section does not move a weld.
    girder = three_run_girder()
    th.save(seeded_book, reading(station_ft=10.0, remaining_in=1.20))
    reduced = th.measured_girder(seeded_book, NUMBER, girder)
    assert reduced.details == girder.details
    assert reduced.girder_id == girder.girder_id


def test_a_schedule_can_be_mapped_run_by_run() -> None:
    girder = three_run_girder()
    mapped = girder.schedule.mapped(lambda run: run.section)
    assert mapped.sections() == girder.schedule.sections()
    assert mapped.transitions_ft == girder.schedule.transitions_ft


def test_mapping_a_schedule_keeps_its_label_and_its_runs() -> None:
    schedule = three_run_girder().schedule
    mapped = schedule.mapped(lambda run: run.section)
    assert mapped.label == schedule.label
    assert len(mapped) == len(schedule)
    assert mapped.length_ft == pytest.approx(schedule.length_ft)


def test_every_girder_on_a_structure_is_reduced(book: Path) -> None:
    inventory.save(book, whole_structure())
    th.save(book, reading(station_ft=10.0, remaining_in=1.20, girder_id="G1"))
    reduced = th.measured_structure(book, inventory.load(book, NUMBER))
    assert reduced.girder("G1").section_at(10.0).plate("bottom").height_in == pytest.approx(1.20)
    assert reduced.girder("G2").section_at(10.0).plate("bottom").height_in == pytest.approx(1.5)


def test_a_structure_nobody_has_measured_comes_back_as_it_was(book: Path) -> None:
    inventory.save(book, whole_structure())
    loaded = inventory.load(book, NUMBER)
    assert th.measured_structure(book, loaded) is loaded


def test_the_reduced_structure_keeps_its_identity(book: Path) -> None:
    inventory.save(book, whole_structure())
    th.save(book, reading(station_ft=10.0, remaining_in=1.20, girder_id="G1"))
    loaded = inventory.load(book, NUMBER)
    reduced = th.measured_structure(book, loaded)
    assert str(reduced.number) == NUMBER
    assert reduced.girder_count == loaded.girder_count
    assert reduced.length_ft == pytest.approx(loaded.length_ft)


def whole_structure() -> Structure:
    """Two girders on one span, so a reading on one can be seen not to reach
    the other."""
    return Structure(
        number=parse(NUMBER),
        name="Salt Fork Creek",
        spans=simple(120.0),
        girders=(
            plain_girder("G1", 0),
            plain_girder("G2", 1),
        ),
        year_built=1968,
    )


def plain_girder(girder_id: str, index: int) -> GirderLine:
    return GirderLine(
        girder_id=girder_id,
        schedule=uniform(girder_id, section(), 120.0),
        layout=DeckLayout(
            girder_index=index,
            spacing_left_ft=7.5,
            spacing_right_ft=7.5,
            overhang_ft=0.0,
            slab_thickness_in=8.0,
        ),
        deck=DeckSlab(thickness_in=8.0, effective_width_in=90.0, haunch_in=2.0, fc_ksi=4.0),
    )
