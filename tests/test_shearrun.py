"""The shear run, and the four ways it is not the moment run with a word changed.

The test that earns its place here is the one about the end stations. A shear
run that borrows the moment run's station list drops the abutment, which is
where shear governs, and every number it does report is correct.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from shearstud.analysis import ratingrun as rr
from shearstud.analysis import shearrun as sr
from shearstud.analysis.ratingrun import RatingSettings
from shearstud.errors import InputError
from shearstud.geometry.composite import DeckSlab
from shearstud.geometry.effective import DeckLayout
from shearstud.geometry.plate import flange, web
from shearstud.geometry.schedule import uniform
from shearstud.geometry.section import Section
from shearstud.loads import vehicles
from shearstud.rating import factors as fac
from shearstud.store import assessment as asm
from shearstud.store import db, inventory
from shearstud.structure.girder import GirderLine
from shearstud.structure.identity import parse
from shearstud.structure.record import Structure
from shearstud.structure.span import series, simple

pytestmark = pytest.mark.rating

SPAN_FT = 90.0
NUMBER = "18-SH-0473"


def section(label: str, web_in: float = 0.5625) -> Section:
    return Section(
        label,
        (
            flange("bottom", width_in=18.0, thickness_in=1.5, y_center_in=0.75),
            web("web", thickness_in=web_in, depth_in=52.0, y_center_in=27.5),
            flange("top", width_in=16.0, thickness_in=1.0, y_center_in=54.0),
        ),
    )


def layout(index: int, exterior: bool) -> DeckLayout:
    if exterior:
        return DeckLayout(
            girder_index=index,
            spacing_left_ft=0.0,
            spacing_right_ft=8.0,
            overhang_ft=3.5,
            slab_thickness_in=8.0,
        )
    return DeckLayout(
        girder_index=index,
        spacing_left_ft=8.0,
        spacing_right_ft=8.0,
        overhang_ft=0.0,
        slab_thickness_in=8.0,
    )


def girder(
    girder_id: str, index: int, exterior: bool, web_in: float = 0.5625, length_ft: float = SPAN_FT
) -> GirderLine:
    return GirderLine(
        girder_id=girder_id,
        schedule=uniform(girder_id, section(girder_id, web_in), length_ft),
        layout=layout(index, exterior),
        deck=DeckSlab(thickness_in=8.0, effective_width_in=90.0, haunch_in=2.0, fc_ksi=4.0),
    )


def structure(continuous: bool = False) -> Structure:
    if continuous:
        spans = series([SPAN_FT, SPAN_FT], continuous=True)
        length_ft = 2.0 * SPAN_FT
    else:
        spans = simple(SPAN_FT)
        length_ft = SPAN_FT
    return Structure(
        number=parse(NUMBER),
        name="Salt Fork Creek",
        spans=spans,
        girders=(
            girder("G1", 0, True, length_ft=length_ft),
            girder("G2", 1, False, length_ft=length_ft),
            girder("G3", 2, False, length_ft=length_ft),
            girder("G4", 3, True, length_ft=length_ft),
        ),
        year_built=1968,
    )


def settings(**overrides: object) -> RatingSettings:
    fields: dict[str, object] = {"stations_per_span": 4}
    fields.update(overrides)
    return RatingSettings(**fields)  # type: ignore[arg-type]


def test_the_ends_are_rated() -> None:
    stations = sr.shear_stations(structure(), settings())
    assert stations[0] == pytest.approx(sr.END_OFFSET_FT)
    assert stations[-1] == pytest.approx(SPAN_FT - sr.END_OFFSET_FT)


def test_the_moment_run_does_not_rate_the_ends() -> None:
    # This is the whole reason there is a separate station list.
    moment = [
        station for station in rr.stations_for(structure(), settings()) if 0.0 < station < SPAN_FT
    ]
    assert min(moment) > sr.END_OFFSET_FT


def test_the_interior_stations_are_the_moment_ones() -> None:
    shear = set(sr.shear_stations(structure(), settings()))
    moment = {
        station
        for station in rr.stations_for(structure(), settings())
        if sr.END_OFFSET_FT < station < SPAN_FT - sr.END_OFFSET_FT
    }
    assert moment <= shear


def test_a_two_span_unit_gets_stations_in_both_spans() -> None:
    stations = sr.shear_stations(structure(continuous=True), settings())
    assert any(station < SPAN_FT for station in stations)
    assert any(station > SPAN_FT for station in stations)


def test_the_stations_come_back_in_order_and_without_duplicates() -> None:
    stations = sr.shear_stations(structure(), settings())
    assert stations == sorted(set(stations))


def test_shear_is_largest_at_the_end() -> None:
    results = sr.rate_structure(structure(), vehicles.legal_fleet(), settings())
    ends = [r for r in results if r.is_at_an_end]
    middles = [r for r in results if not r.is_at_an_end and r.station_ft > 40.0]
    assert min(r.governing.value for r in ends) < min(r.governing.value for r in middles)


def test_the_governing_station_is_an_end_station() -> None:
    results = sr.rate_structure(structure(), vehicles.legal_fleet(), settings())
    worst = sr.governing(results)
    at_ends = {r.governing.label for r in results if r.is_at_an_end}
    assert worst.label in at_ends


def test_the_end_station_knows_it_is_one() -> None:
    results = sr.rate_structure(structure(), vehicles.legal_fleet(), settings())
    assert results[0].is_at_an_end
    assert not results[2].is_at_an_end


def test_the_shear_distribution_factor_is_not_the_moment_one() -> None:
    # No stiffness term in the shear equation, and the two do not agree.
    interior = girder("G2", 1, False)
    moment = rr.distribution_for(structure(), interior, settings())
    shear = sr.distribution_for(interior, settings())
    assert shear != pytest.approx(moment)


def test_an_exterior_girder_carries_at_least_as_much_shear() -> None:
    assert sr.distribution_for(girder("G1", 0, True), settings()) >= sr.distribution_for(
        girder("G2", 1, False), settings()
    )


def test_a_thinner_web_carries_less_shear() -> None:
    thick = sr.rate_station(
        structure(), girder("G2", 1, False, web_in=0.75), 1.0, vehicles.legal_fleet(), settings()
    )
    thin = sr.rate_station(
        structure(), girder("G2", 1, False, web_in=0.375), 1.0, vehicles.legal_fleet(), settings()
    )
    assert thin.capacity_kip < thick.capacity_kip
    assert thin.governing.value < thick.governing.value


def test_a_thinner_web_is_more_slender() -> None:
    thick = sr.rate_station(
        structure(), girder("G2", 1, False, web_in=0.75), 1.0, vehicles.legal_fleet(), settings()
    )
    thin = sr.rate_station(
        structure(), girder("G2", 1, False, web_in=0.375), 1.0, vehicles.legal_fleet(), settings()
    )
    assert thin.web_slenderness > thick.web_slenderness
    assert thin.web_slenderness == pytest.approx(52.0 / 0.375)


def test_a_station_carries_one_rating_per_vehicle() -> None:
    fleet = vehicles.legal_fleet()
    station = sr.rate_station(structure(), girder("G2", 1, False), 1.0, fleet, settings())
    assert len(station.ratings) == len(fleet)
    assert {r.vehicle for r in station.ratings} == {v.name for v in fleet}


def test_the_governing_vehicle_at_a_station_is_the_worst_one() -> None:
    station = sr.rate_station(
        structure(), girder("G2", 1, False), 1.0, vehicles.legal_fleet(), settings()
    )
    assert station.governing.value == min(r.value for r in station.ratings)


def test_a_station_with_no_ratings_has_no_governing_one() -> None:
    empty = sr.ShearRating(
        girder_id="G2",
        station_ft=1.0,
        distribution_factor=0.7,
        capacity_kip=400.0,
        dead_component_kip=30.0,
        dead_surface_kip=5.0,
        web_slenderness=92.0,
    )
    with pytest.raises(InputError, match="has no shear ratings"):
        _ = empty.governing


def test_a_run_with_no_vehicles_is_refused() -> None:
    with pytest.raises(InputError, match="needs at least one vehicle"):
        sr.rate_station(structure(), girder("G2", 1, False), 1.0, [], settings())


def test_asking_for_the_governing_rating_of_nothing_is_refused() -> None:
    with pytest.raises(InputError, match="nothing was rated in shear"):
        sr.governing([])


def test_the_dead_load_shear_falls_from_the_end_to_midspan() -> None:
    at_end = sr.dead_load_at(structure(), girder("G2", 1, False), 1.0, settings())
    at_mid = sr.dead_load_at(structure(), girder("G2", 1, False), SPAN_FT / 2.0, settings())
    assert at_end.component > at_mid.component
    assert at_mid.component == pytest.approx(0.0, abs=1.0e-9)


def test_the_wearing_surface_is_kept_apart_from_the_rest() -> None:
    dead = sr.dead_load_at(structure(), girder("G2", 1, False), 1.0, settings(overlay_in=3.0))
    assert dead.wearing_surface > 0.0
    assert dead.component > dead.wearing_surface


def test_a_continuous_unit_gets_a_line_that_goes_negative() -> None:
    line = sr.influence_for(structure(continuous=True), SPAN_FT + 20.0)
    assert min(line.ordinates) < 0.0


def test_a_continuous_line_covers_the_whole_unit() -> None:
    line = sr.influence_for(structure(continuous=True), SPAN_FT + 20.0)
    assert line.end_ft == pytest.approx(2.0 * SPAN_FT)


def test_a_simple_span_line_covers_one_span() -> None:
    line = sr.influence_for(structure(), 45.0)
    assert line.start_ft == pytest.approx(0.0)
    assert line.end_ft == pytest.approx(SPAN_FT)


def test_the_simple_shear_line_jumps_at_the_section() -> None:
    # The jump is why the run reads both directions and takes the larger.
    line = sr.influence_for(structure(), 45.0)
    at_section = [o for s, o in zip(line.stations_ft, line.ordinates, strict=True) if s == 45.0]
    assert len(at_section) == 2
    assert at_section[1] - at_section[0] == pytest.approx(1.0)


def test_every_girder_is_rated_at_every_station() -> None:
    results = sr.rate_structure(structure(), vehicles.legal_fleet(), settings())
    stations = sr.shear_stations(structure(), settings())
    assert len(results) == 4 * len(stations)


def test_a_shear_run_can_be_written_into_the_book(book: Path) -> None:
    inventory.save(book, structure())
    results = sr.rate_structure(structure(), vehicles.legal_fleet(), settings())
    written = sr.store(book, NUMBER, results, fac.OPERATING, date(2026, 5, 4))
    assert written == sum(len(station.ratings) for station in results)
    assert db.row_count(book, "ratings") == written


def test_the_stored_rows_are_shear_ratings(book: Path) -> None:
    inventory.save(book, structure())
    results = sr.rate_structure(structure(), vehicles.legal_fleet(), settings())
    sr.store(book, NUMBER, results, fac.OPERATING, date(2026, 5, 4))
    assert {row.effect for row in asm.load_ratings(book, NUMBER)} == {sr.EFFECT_SHEAR}


def test_shear_and_moment_ratings_live_together_in_the_book(book: Path) -> None:
    inventory.save(book, structure())
    moment = rr.rate_structure(structure(), vehicles.legal_fleet(), settings())
    shear = sr.rate_structure(structure(), vehicles.legal_fleet(), settings())
    rr.store(book, NUMBER, moment, fac.OPERATING, date(2026, 5, 4))
    sr.store(book, NUMBER, shear, fac.OPERATING, date(2026, 5, 4))
    effects = {row.effect for row in asm.load_ratings(book, NUMBER)}
    assert effects == {rr.EFFECT_MOMENT, sr.EFFECT_SHEAR}


def test_a_level_nobody_rates_at_is_refused(book: Path) -> None:
    with pytest.raises(InputError, match="unknown rating level"):
        sr.store(book, NUMBER, [], "provisional", date(2026, 5, 4))


def test_storing_nothing_writes_nothing(book: Path) -> None:
    assert sr.store(book, NUMBER, [], fac.OPERATING, date(2026, 5, 4)) == 0
