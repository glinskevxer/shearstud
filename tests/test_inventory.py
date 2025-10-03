"""Saving and loading a whole structure, and the round trip that has to hold."""

from __future__ import annotations

from pathlib import Path

import pytest

from shearstud.errors import StorageError
from shearstud.geometry.composite import DeckSlab
from shearstud.geometry.effective import DeckLayout
from shearstud.geometry.plate import flange, web
from shearstud.geometry.schedule import from_breaks, uniform
from shearstud.geometry.section import Section
from shearstud.store import db, inventory, migrate
from shearstud.store.inventory import StructurePolicy
from shearstud.structure.detail import FIBRE_BOTTOM, FatigueDetail
from shearstud.structure.girder import GirderLine
from shearstud.structure.identity import parse
from shearstud.structure.record import Structure
from shearstud.structure.span import series, simple

pytestmark = pytest.mark.store

UNIT_FT = 120.0


@pytest.fixture
def book(tmp_path: Path) -> Path:
    path = tmp_path / "shearstud.sqlite3"
    migrate.upgrade(path)
    return path


def section(label: str, bottom_in: float) -> Section:
    return Section(
        label,
        (
            flange("bottom", width_in=16.0, thickness_in=bottom_in, y_center_in=bottom_in / 2.0),
            web("web", thickness_in=0.5, depth_in=48.0, y_center_in=bottom_in + 24.0),
            flange("top", width_in=14.0, thickness_in=1.0, y_center_in=bottom_in + 48.5),
        ),
    )


def layout(index: int, exterior: bool) -> DeckLayout:
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


def deck() -> DeckSlab:
    return DeckSlab(thickness_in=8.0, effective_width_in=90.0, haunch_in=2.0, fc_ksi=4.0)


def detail(detail_id: str, station_ft: float, note: str = "") -> FatigueDetail:
    return FatigueDetail(
        detail_id=detail_id,
        kind="cover_plate_end",
        category_name="E",
        station_ft=station_ft,
        fibre=FIBRE_BOTTOM,
        note=note,
    )


def girder(
    girder_id: str, index: int, exterior: bool = False, prefix: str = "18SH0473"
) -> GirderLine:
    if index == 1:
        schedule = from_breaks(
            girder_id,
            [section("end", 1.0), section("middle", 2.0), section("far", 1.0)],
            [30.0, 90.0],
            UNIT_FT,
        )
    else:
        schedule = uniform(girder_id, section("only", 1.25), UNIT_FT)
    return GirderLine(
        girder_id=girder_id,
        schedule=schedule,
        layout=layout(index, exterior),
        deck=deck(),
        details=(detail(f"{prefix}-{girder_id}-D1", 24.5, "cover plate end, ground"),),
    )


def structure() -> Structure:
    return Structure(
        number=parse("18-SH-0473"),
        name="Salt Fork Creek",
        spans=simple(UNIT_FT),
        girders=(
            girder("G1", 0, exterior=True),
            girder("G2", 1),
            girder("G3", 2),
            girder("G4", 3, exterior=True),
        ),
        year_built=1968,
        effective_width_rule="legacy",
    )


def test_a_saved_structure_comes_back_the_same(book: Path) -> None:
    original = structure()
    inventory.save(book, original)
    loaded = inventory.load(book, "18-SH-0473")
    assert str(loaded.number) == str(original.number)
    assert loaded.name == original.name
    assert loaded.year_built == original.year_built
    assert loaded.effective_width_rule == "legacy"


def test_the_span_arrangement_round_trips(book: Path) -> None:
    original = Structure(
        number=parse("07-CR-1204"),
        name="Dry Creek",
        spans=series([84.0, 105.0, 84.0], continuous=True),
        girders=(
            GirderLine(
                girder_id="G1",
                schedule=uniform("G1", section("only", 1.0), 273.0),
                layout=layout(0, exterior=True),
                deck=deck(),
            ),
        ),
    )
    inventory.save(book, original)
    loaded = inventory.load(book, "07-CR-1204")
    assert loaded.spans.lengths_ft == pytest.approx((84.0, 105.0, 84.0))
    assert loaded.spans.continuous


def test_every_girder_comes_back_in_index_order(book: Path) -> None:
    inventory.save(book, structure())
    loaded = inventory.load(book, "18-SH-0473")
    assert [g.girder_id for g in loaded] == ["G1", "G2", "G3", "G4"]


def test_the_section_schedule_round_trips(book: Path) -> None:
    inventory.save(book, structure())
    loaded = inventory.load(book, "18-SH-0473")
    schedule = loaded.girder("G2").schedule
    assert len(schedule) == 3
    assert schedule.transitions_ft == pytest.approx((30.0, 90.0))
    assert [s.label for s in schedule.sections()] == ["end", "middle", "far"]


def test_the_section_properties_survive_the_round_trip(book: Path) -> None:
    original = structure()
    inventory.save(book, original)
    loaded = inventory.load(book, "18-SH-0473")
    before = original.girder("G2").section_at(60.0)
    after = loaded.girder("G2").section_at(60.0)
    assert after.inertia_in4 == pytest.approx(before.inertia_in4)
    assert after.section_modulus_bottom_in3 == pytest.approx(before.section_modulus_bottom_in3)


def test_the_details_round_trip_with_their_notes(book: Path) -> None:
    inventory.save(book, structure())
    loaded = inventory.load(book, "18-SH-0473")
    d = loaded.girder("G3").detail("18SH0473-G3-D1")
    assert d.category_name == "E"
    assert d.station_ft == pytest.approx(24.5)
    assert d.note == "cover plate end, ground"


def test_the_layout_round_trips_including_the_overhang(book: Path) -> None:
    inventory.save(book, structure())
    loaded = inventory.load(book, "18-SH-0473")
    assert loaded.girder("G1").is_exterior
    assert loaded.girder("G1").layout.overhang_ft == pytest.approx(3.0)
    assert not loaded.girder("G2").is_exterior


def test_the_deck_round_trips(book: Path) -> None:
    inventory.save(book, structure())
    loaded = inventory.load(book, "18-SH-0473")
    assert loaded.girder("G2").deck.fc_ksi == pytest.approx(4.0)
    assert loaded.girder("G2").deck.haunch_in == pytest.approx(2.0)


def test_saving_twice_replaces_rather_than_duplicating(book: Path) -> None:
    inventory.save(book, structure())
    inventory.save(book, structure())
    assert len(db.fetch_all(book, "SELECT number FROM structures")) == 1
    assert len(db.fetch_all(book, "SELECT girder_id FROM girders")) == 4


def test_saving_a_smaller_structure_removes_what_it_dropped(book: Path) -> None:
    inventory.save(book, structure())
    trimmed = Structure(
        number=parse("18-SH-0473"),
        name="Salt Fork Creek",
        spans=simple(UNIT_FT),
        girders=(girder("G1", 0, exterior=True),),
        year_built=1968,
    )
    inventory.save(book, trimmed)
    assert len(inventory.load(book, "18-SH-0473").girders) == 1
    assert len(db.fetch_all(book, "SELECT detail_id FROM details")) == 1


def test_the_policy_fields_are_written(book: Path) -> None:
    policy = StructurePolicy(
        steel_grade="A572-50",
        member_condition="fair",
        redundancy="limited",
        adtt=2400.0,
        lanes_available=3,
        growth_pct_per_yr=1.8,
    )
    inventory.save(book, structure(), policy)
    row = db.fetch_one(
        book,
        "SELECT steel_grade, member_condition, adtt FROM structures WHERE number = ?",
        ("18-SH-0473",),
    )
    assert row is not None
    assert row["steel_grade"] == "A572-50"
    assert row["member_condition"] == "fair"
    assert row["adtt"] == pytest.approx(2400.0)


def test_the_policy_defaults_are_written_when_none_is_given(book: Path) -> None:
    inventory.save(book, structure())
    row = db.fetch_one(
        book, "SELECT steel_grade, redundancy FROM structures WHERE number = ?", ("18-SH-0473",)
    )
    assert row is not None
    assert row["steel_grade"] == "A36"
    assert row["redundancy"] == "redundant"


def test_a_policy_with_negative_traffic_is_refused() -> None:
    with pytest.raises(StorageError, match="is negative"):
        StructurePolicy(adtt=-1.0)


def test_a_policy_with_no_lanes_is_refused() -> None:
    with pytest.raises(StorageError, match="is not a roadway"):
        StructurePolicy(lanes_available=0)


def test_loading_a_structure_that_is_not_there_is_refused(book: Path) -> None:
    with pytest.raises(StorageError, match="no structure"):
        inventory.load(book, "99-IH-0001")


def test_the_numbers_come_back_in_file_cabinet_order(book: Path) -> None:
    inventory.save(book, structure())
    second = Structure(
        number=parse("07-CR-1204"),
        name="Dry Creek",
        spans=simple(UNIT_FT),
        girders=(girder("G1", 0, exterior=True, prefix="07CR1204"),),
    )
    inventory.save(book, second)
    assert inventory.numbers(book) == ["07-CR-1204", "18-SH-0473"]


def test_two_structures_cannot_share_a_detail_id(book: Path) -> None:
    # Detail ids are inventory wide, because a gauge names one and a gauge is
    # not scoped to a structure.
    import sqlite3

    inventory.save(book, structure())
    clash = Structure(
        number=parse("07-CR-1204"),
        name="Dry Creek",
        spans=simple(UNIT_FT),
        girders=(girder("G1", 0, exterior=True),),
    )
    with pytest.raises(sqlite3.IntegrityError):
        inventory.save(book, clash)


def test_existence_can_be_asked_without_loading(book: Path) -> None:
    inventory.save(book, structure())
    assert inventory.exists(book, "18-SH-0473")
    assert not inventory.exists(book, "99-IH-0001")


def test_deleting_takes_everything_with_it(book: Path) -> None:
    inventory.save(book, structure())
    inventory.delete(book, "18-SH-0473")
    assert not inventory.exists(book, "18-SH-0473")
    assert db.fetch_all(book, "SELECT girder_id FROM girders") == []
    assert db.fetch_all(book, "SELECT detail_id FROM details") == []
    assert db.fetch_all(book, "SELECT plate_label FROM section_plates") == []


def test_deleting_something_that_is_not_there_is_refused(book: Path) -> None:
    with pytest.raises(StorageError, match="no structure"):
        inventory.delete(book, "99-IH-0001")


def test_the_book_stays_consistent_after_a_save_and_a_delete(book: Path) -> None:
    inventory.save(book, structure())
    inventory.delete(book, "18-SH-0473")
    assert db.foreign_key_violations(book) == []
    assert db.integrity_check(book) == []
