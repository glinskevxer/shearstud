"""The rating run, which is where every other module gets used at once."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from shearstud.analysis import ratingrun as rr
from shearstud.analysis.ratingrun import RatingSettings
from shearstud.errors import InputError, StorageError
from shearstud.geometry.composite import DeckSlab
from shearstud.geometry.effective import DeckLayout
from shearstud.geometry.plate import flange, web
from shearstud.geometry.schedule import from_breaks, uniform
from shearstud.geometry.section import Section
from shearstud.loads import distribution as dist
from shearstud.loads import vehicles
from shearstud.rating import factors as fac
from shearstud.store import assessment as asm
from shearstud.store import db, inventory
from shearstud.store.inventory import StructurePolicy
from shearstud.structure.girder import GirderLine
from shearstud.structure.identity import parse
from shearstud.structure.record import Structure
from shearstud.structure.span import series, simple

pytestmark = pytest.mark.rating

SPAN_FT = 90.0


def section(label: str, bottom_in: float) -> Section:
    return Section(
        label,
        (
            flange("bottom", width_in=18.0, thickness_in=bottom_in, y_center_in=bottom_in / 2.0),
            web("web", thickness_in=0.5625, depth_in=52.0, y_center_in=bottom_in + 26.0),
            flange("top", width_in=16.0, thickness_in=1.0, y_center_in=bottom_in + 52.5),
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


def girder(girder_id: str, index: int, exterior: bool, length_ft: float = SPAN_FT) -> GirderLine:
    if index == 1:
        schedule = from_breaks(
            girder_id,
            [section("end", 1.25), section("middle", 2.0), section("far", 1.25)],
            [length_ft * 0.25, length_ft * 0.75],
            length_ft,
        )
    else:
        schedule = uniform(girder_id, section("only", 1.5), length_ft)
    return GirderLine(
        girder_id=girder_id,
        schedule=schedule,
        layout=layout(index, exterior),
        deck=DeckSlab(thickness_in=8.0, effective_width_in=96.0, haunch_in=2.0, fc_ksi=4.0),
    )


def structure(continuous: bool = False) -> Structure:
    if continuous:
        spans = series([SPAN_FT, SPAN_FT], continuous=True)
        length_ft = 2.0 * SPAN_FT
    else:
        spans = simple(SPAN_FT)
        length_ft = SPAN_FT
    return Structure(
        number=parse("18-SH-0473"),
        name="Salt Fork Creek",
        spans=spans,
        girders=(
            girder("G1", 0, True, length_ft),
            girder("G2", 1, False, length_ft),
            girder("G3", 2, False, length_ft),
            girder("G4", 3, True, length_ft),
        ),
        year_built=1968,
    )


def test_the_stations_are_the_tenth_points() -> None:
    got = rr.stations_for(structure(), RatingSettings())
    assert len(got) == 11
    assert got[0] == pytest.approx(0.0)
    assert got[-1] == pytest.approx(SPAN_FT)
    assert got[5] == pytest.approx(SPAN_FT / 2.0)


def test_a_two_span_unit_gets_stations_in_both_spans() -> None:
    got = rr.stations_for(structure(continuous=True), RatingSettings())
    assert len(got) == 21
    assert got[-1] == pytest.approx(2.0 * SPAN_FT)


def test_a_finer_sampling_gives_more_stations() -> None:
    got = rr.stations_for(structure(), RatingSettings(stations_per_span=20))
    assert len(got) == 21


def test_too_few_stations_is_refused() -> None:
    with pytest.raises(InputError, match="too few to find a maximum"):
        RatingSettings(stations_per_span=1)


def test_an_unknown_steel_grade_is_caught_at_the_settings() -> None:
    with pytest.raises(InputError, match="unknown steel grade"):
        RatingSettings(steel_grade="A992")


def test_an_unknown_condition_is_caught_at_the_settings() -> None:
    with pytest.raises(InputError, match="unknown member condition"):
        RatingSettings(member_condition="serviceable")


def test_no_lanes_loaded_is_refused() -> None:
    with pytest.raises(InputError, match="not a load case"):
        RatingSettings(lanes_loaded=0)


def test_a_simple_span_gets_a_simple_influence_line() -> None:
    il = rr.influence_for(structure(), SPAN_FT / 2.0)
    assert il.peak == pytest.approx(SPAN_FT / 4.0)


def test_a_continuous_unit_gets_a_line_that_goes_negative() -> None:
    il = rr.influence_for(structure(continuous=True), SPAN_FT / 2.0)
    assert il.trough < 0.0


def test_the_distribution_factor_lands_where_a_sheet_puts_it() -> None:
    s = structure()
    got = rr.distribution_for(s, s.girder("G2"), RatingSettings())
    assert 0.5 < got < 1.0


def test_an_exterior_girder_carries_at_least_as_much_as_an_interior_one() -> None:
    s = structure()
    settings = RatingSettings()
    interior = rr.distribution_for(s, s.girder("G3"), settings)
    exterior = rr.distribution_for(s, s.girder("G4"), settings)
    assert exterior >= interior


def test_the_dead_load_is_bigger_at_a_stiffer_section() -> None:
    s = structure()
    settings = RatingSettings(overlay_in=3.0)
    thin = rr.dead_load_at(s, s.girder("G2"), 9.0, settings)
    thick = rr.dead_load_at(s, s.girder("G2"), 45.0, settings)
    assert thick.component > thin.component


def test_the_wearing_surface_is_kept_apart_from_the_rest() -> None:
    s = structure()
    with_overlay = rr.dead_load_at(s, s.girder("G2"), 45.0, RatingSettings(overlay_in=3.0))
    without = rr.dead_load_at(s, s.girder("G2"), 45.0, RatingSettings(overlay_in=0.0))
    assert with_overlay.wearing_surface > 0.0
    assert without.wearing_surface == pytest.approx(0.0)
    assert with_overlay.component == pytest.approx(without.component)


def test_a_station_rating_carries_one_result_per_vehicle() -> None:
    s = structure()
    fleet = vehicles.legal_fleet()
    got = rr.rate_station(s, s.girder("G2"), SPAN_FT / 2.0, fleet, RatingSettings())
    assert len(got.ratings) == len(fleet)
    assert {r.vehicle for r in got.ratings} == {t.name for t in fleet}


def test_a_station_rating_keeps_its_workings() -> None:
    s = structure()
    got = rr.rate_station(
        s, s.girder("G2"), SPAN_FT / 2.0, vehicles.legal_fleet(), RatingSettings(overlay_in=3.0)
    )
    assert got.girder_id == "G2"
    assert got.station_ft == pytest.approx(SPAN_FT / 2.0)
    assert got.capacity_kipft > 0.0
    assert got.dead_component_kipft > 0.0
    assert got.dead_surface_kipft > 0.0
    assert 0.0 < got.distribution_factor < 2.0


def test_the_governing_vehicle_at_a_station_is_the_worst_one() -> None:
    s = structure()
    got = rr.rate_station(
        s, s.girder("G2"), SPAN_FT / 2.0, vehicles.legal_fleet(), RatingSettings()
    )
    worst = got.governing
    assert all(worst.value <= r.value + 1e-12 for r in got.ratings)


def test_a_station_with_no_vehicles_is_refused() -> None:
    s = structure()
    with pytest.raises(InputError, match="at least one vehicle"):
        rr.rate_station(s, s.girder("G2"), SPAN_FT / 2.0, [], RatingSettings())


def test_a_station_rating_with_no_results_cannot_be_asked_for_a_governing_one() -> None:
    empty = rr.StationRating("G2", 45.0, 0.7, 5000.0, 900.0, 100.0)
    with pytest.raises(InputError, match="has no ratings"):
        _ = empty.governing


def test_a_whole_run_covers_every_girder() -> None:
    s = structure()
    results = rr.rate_structure(s, vehicles.legal_fleet(), RatingSettings(stations_per_span=4))
    assert {station.girder_id for station in results} == {"G1", "G2", "G3", "G4"}


def test_a_whole_run_skips_the_abutments() -> None:
    s = structure()
    results = rr.rate_structure(s, vehicles.legal_fleet(), RatingSettings(stations_per_span=4))
    for station in results:
        assert 0.0 < station.station_ft < s.length_ft


def test_a_typical_structure_rates_above_one_for_the_legal_fleet() -> None:
    s = structure()
    results = rr.rate_structure(s, vehicles.legal_fleet(), RatingSettings(stations_per_span=4))
    assert rr.governing(results).value > 1.0


def test_a_poor_non_redundant_structure_rates_lower() -> None:
    s = structure()
    good = rr.rate_structure(s, vehicles.legal_fleet(), RatingSettings(stations_per_span=4))
    poor = rr.rate_structure(
        s,
        vehicles.legal_fleet(),
        RatingSettings(stations_per_span=4, member_condition="poor", redundancy="non_redundant"),
    )
    assert rr.governing(poor).value < rr.governing(good).value


def test_an_overlay_lowers_the_rating() -> None:
    s = structure()
    bare = rr.rate_structure(s, vehicles.legal_fleet(), RatingSettings(stations_per_span=4))
    paved = rr.rate_structure(
        s, vehicles.legal_fleet(), RatingSettings(stations_per_span=4, overlay_in=4.0)
    )
    assert rr.governing(paved).value < rr.governing(bare).value


def test_a_rough_riding_surface_lowers_the_rating() -> None:
    s = structure()
    smooth = rr.rate_structure(
        s, vehicles.legal_fleet(), RatingSettings(stations_per_span=4, riding_surface="smooth")
    )
    rough = rr.rate_structure(
        s, vehicles.legal_fleet(), RatingSettings(stations_per_span=4, riding_surface="rough")
    )
    assert rr.governing(rough).value < rr.governing(smooth).value


def test_the_design_load_is_harsher_than_the_legal_fleet() -> None:
    s = structure()
    settings = RatingSettings(stations_per_span=4)
    legal = rr.rate_structure(s, vehicles.legal_fleet(), settings)
    design = rr.rate_structure(
        s, [vehicles.design_truck()], settings, legal=False, level="inventory"
    )
    assert rr.governing(design).value < rr.governing(legal).value


def test_the_governing_station_is_near_midspan() -> None:
    s = structure()
    results = rr.rate_structure(s, vehicles.legal_fleet(), RatingSettings(stations_per_span=10))
    worst = min(results, key=lambda station: station.governing.value)
    assert 0.3 * SPAN_FT < worst.station_ft < 0.7 * SPAN_FT


def test_a_continuous_unit_runs_through_without_error() -> None:
    s = structure(continuous=True)
    results = rr.rate_structure(s, vehicles.legal_fleet(), RatingSettings(stations_per_span=4))
    assert results
    assert rr.governing(results).value > 0.0


def test_governing_over_nothing_is_refused() -> None:
    with pytest.raises(InputError, match="nothing was rated"):
        rr.governing([])


def rated() -> list[rr.StationRating]:
    """One structure rated against the legal fleet, at a coarse sampling."""
    return rr.rate_structure(
        structure(), vehicles.legal_fleet(), RatingSettings(stations_per_span=2)
    )


def stored(book: Path, level: str = fac.OPERATING) -> int:
    inventory.save(book, structure())
    return rr.store(book, "18-SH-0473", rated(), level, date(2026, 5, 4))


def test_a_run_can_be_written_into_the_book(book: Path) -> None:
    written = stored(book)
    assert written > 0
    assert db.row_count(book, "ratings") == written


def test_every_vehicle_at_every_station_is_written(book: Path) -> None:
    results = rated()
    expected = sum(len(station.ratings) for station in results)
    assert stored(book) == expected


def test_the_stored_rows_carry_the_girder_and_the_station(book: Path) -> None:
    stored(book)
    rows = asm.load_ratings(book, "18-SH-0473")
    assert {row.girder_id for row in rows} == {"G1", "G2", "G3", "G4"}
    assert all(row.station_ft >= 0.0 for row in rows)


def test_the_stored_rows_carry_the_date_they_were_given(book: Path) -> None:
    stored(book)
    assert asm.latest_rating_date(book, "18-SH-0473") == date(2026, 5, 4)


def test_the_stored_rows_are_moment_ratings(book: Path) -> None:
    stored(book)
    assert {row.effect for row in asm.load_ratings(book, "18-SH-0473")} == {rr.EFFECT_MOMENT}


def test_the_level_asked_for_is_the_level_written(book: Path) -> None:
    stored(book, fac.INVENTORY)
    assert {row.level for row in asm.load_ratings(book, "18-SH-0473")} == {fac.INVENTORY}


def test_the_governing_row_in_the_book_matches_the_run(book: Path) -> None:
    stored(book)
    assert asm.governing_rating(book, "18-SH-0473").rating_factor == pytest.approx(
        rr.governing(rated()).value
    )


def test_a_level_nobody_rates_at_is_refused(book: Path) -> None:
    with pytest.raises(InputError, match="unknown rating level"):
        rr.store(book, "18-SH-0473", rated(), "provisional", date(2026, 5, 4))


def test_storing_nothing_writes_nothing(book: Path) -> None:
    assert rr.store(book, "18-SH-0473", [], fac.OPERATING, date(2026, 5, 4)) == 0


def test_both_levels_the_rating_package_knows_are_accepted(book: Path) -> None:
    assert set(rr.RATING_LEVELS) == set(fac.LEVELS)


def test_the_settings_are_read_off_the_structure(book: Path) -> None:
    inventory.save(
        book,
        structure(),
        StructurePolicy(steel_grade="A572-50", member_condition="fair", adtt=2400.0),
    )
    settings = rr.settings_for(book, "18-SH-0473")
    assert settings.steel_grade == "A572-50"
    assert settings.member_condition == "fair"
    assert settings.adtt == pytest.approx(2400.0)


def test_an_override_wins_over_the_record(book: Path) -> None:
    inventory.save(book, structure(), StructurePolicy(member_condition="fair"))
    assert rr.settings_for(book, "18-SH-0473", member_condition="poor").member_condition == "poor"


def test_an_override_of_nothing_is_not_an_override(book: Path) -> None:
    # Click hands a missing option through as None, and every command would
    # otherwise have to strip those out for itself.
    inventory.save(book, structure(), StructurePolicy(member_condition="fair"))
    settings = rr.settings_for(book, "18-SH-0473", member_condition=None)
    assert settings.member_condition == "fair"


def test_a_run_setting_can_be_given_without_a_record_field(book: Path) -> None:
    inventory.save(book, structure())
    settings = rr.settings_for(book, "18-SH-0473", stations_per_span=4, overlay_in=2.0)
    assert settings.stations_per_span == 4
    assert settings.overlay_in == pytest.approx(2.0)


def test_a_setting_the_run_does_not_have_is_refused(book: Path) -> None:
    inventory.save(book, structure())
    with pytest.raises(TypeError):
        rr.settings_for(book, "18-SH-0473", riding_conditions="wet")


def test_a_structure_that_is_not_there_has_no_settings(book: Path) -> None:
    with pytest.raises(StorageError, match="no structure"):
        rr.settings_for(book, "99-XX-9999")


def test_a_grade_the_record_does_not_know_is_refused(book: Path) -> None:
    inventory.save(book, structure())
    with pytest.raises(InputError, match="unknown steel grade"):
        rr.settings_for(book, "18-SH-0473", steel_grade="A999")


def test_a_simple_span_has_no_negative_region() -> None:
    unit = structure()
    assert not any(
        rr.is_negative_region(unit, station) for station in rr.stations_for(unit, RatingSettings())
    )


def test_the_station_at_a_pier_is_a_negative_region() -> None:
    assert rr.is_negative_region(structure(continuous=True), SPAN_FT)


def test_a_station_a_quarter_span_from_the_pier_is_still_negative() -> None:
    unit = structure(continuous=True)
    reach_ft = rr.NEGATIVE_REGION_FRAC * SPAN_FT
    assert rr.is_negative_region(unit, SPAN_FT - reach_ft)
    assert rr.is_negative_region(unit, SPAN_FT + reach_ft)


def test_a_station_beyond_the_reach_is_a_positive_region() -> None:
    unit = structure(continuous=True)
    reach_ft = rr.NEGATIVE_REGION_FRAC * SPAN_FT
    assert not rr.is_negative_region(unit, SPAN_FT - reach_ft - 1.0)
    assert not rr.is_negative_region(unit, SPAN_FT + reach_ft + 1.0)


def test_midspan_is_never_a_negative_region() -> None:
    assert not rr.is_negative_region(structure(continuous=True), SPAN_FT / 2.0)


def test_the_pier_section_is_rated_on_bare_steel() -> None:
    # The deck over a pier is in tension and cracked, so it carries nothing.
    unit = structure(continuous=True)
    girder_line = unit.girder("G2")
    over_pier = rr.capacity_at(unit, girder_line, SPAN_FT, RatingSettings())
    at_midspan = rr.capacity_at(unit, girder_line, SPAN_FT / 2.0, RatingSettings())
    assert over_pier.moment_kipft < at_midspan.moment_kipft


def test_the_midspan_section_can_reach_its_plastic_moment() -> None:
    unit = structure(continuous=True)
    at_midspan = rr.capacity_at(unit, unit.girder("G2"), SPAN_FT / 2.0, RatingSettings())
    assert at_midspan.mechanism in ("plastic", "yield")


def test_the_pier_section_never_reaches_its_plastic_moment() -> None:
    unit = structure(continuous=True)
    over_pier = rr.capacity_at(unit, unit.girder("G2"), SPAN_FT, RatingSettings())
    assert over_pier.mechanism == "yield"


def test_a_simple_span_is_rated_composite_everywhere() -> None:
    simple_unit = structure()
    at_midspan = rr.capacity_at(
        simple_unit, simple_unit.girder("G2"), SPAN_FT / 2.0, RatingSettings()
    )
    continuous_unit = structure(continuous=True)
    same = rr.capacity_at(
        continuous_unit, continuous_unit.girder("G2"), SPAN_FT / 2.0, RatingSettings()
    )
    assert at_midspan.moment_kipft == pytest.approx(same.moment_kipft)


def test_a_pier_station_rates_against_the_hogging_placement() -> None:
    # Driving for the maximum finds the sagging placement, which at a pier is
    # smaller than the hogging one and would overstate the rating.
    unit = structure(continuous=True)
    settings = RatingSettings(stations_per_span=4)
    at_pier = rr.rate_station(unit, unit.girder("G2"), SPAN_FT, vehicles.legal_fleet(), settings)
    assert at_pier.governing.factored_live > 0.0
    assert at_pier.governing.value > 0.0


def test_every_rating_on_a_continuous_unit_is_positive() -> None:
    # The live effect goes into the equation as a magnitude. A negative one
    # would come back as a rating factor above one on a section that is failing.
    unit = structure(continuous=True)
    results = rr.rate_structure(unit, vehicles.legal_fleet(), RatingSettings(stations_per_span=4))
    for station in results:
        for factor in station.ratings:
            assert factor.factored_live >= 0.0


def three_girder_structure() -> Structure:
    """A three girder stringer unit, which the fitted equations do not cover."""
    return Structure(
        number=parse("07-CR-0112"),
        name="Dry Creek",
        spans=simple(SPAN_FT),
        girders=(girder("G1", 0, True), girder("G2", 1, False), girder("G3", 2, True)),
        year_built=1954,
    )


def test_a_cross_section_the_equations_do_not_cover_uses_the_lever_rule() -> None:
    # Eleven three girder stringer units on this inventory sit outside the
    # range the equations were fitted in. Extrapolating there is the wrong
    # answer; statics is the right one.
    unit = three_girder_structure()
    factor = rr.distribution_for(unit, unit.girder("G2"), RatingSettings())
    assert 0.0 < factor < 1.5


def test_the_lever_rule_answer_is_the_one_statics_gives() -> None:
    unit = three_girder_structure()
    line = unit.girder("G2")
    assert rr.distribution_for(unit, line, RatingSettings()) == pytest.approx(
        dist.lever_rule_factor(
            line.layout.average_spacing_ft, line.layout.overhang_ft, lanes_loaded=2
        )
    )


def test_a_four_girder_unit_still_uses_the_equations() -> None:
    unit = structure()
    line = unit.girder("G2")
    assert rr.distribution_for(unit, line, RatingSettings()) != pytest.approx(
        dist.lever_rule_factor(
            line.layout.average_spacing_ft, line.layout.overhang_ft, lanes_loaded=2
        )
    )


def test_a_three_girder_unit_rates_end_to_end() -> None:
    # It used to raise, because the applicability check refused before the
    # lever rule was reachable.
    results = rr.rate_structure(
        three_girder_structure(), vehicles.legal_fleet(), RatingSettings(stations_per_span=4)
    )
    assert results
    assert rr.governing(results).value > 0.0


def test_the_riding_surface_is_read_off_the_structure(book: Path) -> None:
    # It used to be a command line option with no home, so every rating
    # started from the default and an engineer who knew the deck was rough
    # had to remember to say so, every time.
    inventory.save(book, structure(), StructurePolicy(riding_surface="rough"))
    assert rr.settings_for(book, "18-SH-0473").riding_surface == "rough"


def test_a_rougher_deck_lowers_the_rating(book: Path) -> None:
    inventory.save(book, structure(), StructurePolicy(riding_surface="smooth"))
    smooth = rr.rate_structure(
        structure(),
        vehicles.legal_fleet(),
        rr.settings_for(book, "18-SH-0473", stations_per_span=4),
    )
    inventory.save(book, structure(), StructurePolicy(riding_surface="rough"))
    rough = rr.rate_structure(
        structure(),
        vehicles.legal_fleet(),
        rr.settings_for(book, "18-SH-0473", stations_per_span=4),
    )
    assert rr.governing(rough).value < rr.governing(smooth).value
