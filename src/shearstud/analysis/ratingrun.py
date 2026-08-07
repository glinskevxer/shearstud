"""Rating a whole structure, which is where every other module gets used.

A rating run is a loop over girders, stations and vehicles, and the interesting
part is what happens once per iteration and what happens once per run:

* the **distribution factor** is per girder, not per station. It reads the span
  length, and on a continuous unit that is the length of the span the section is
  in rather than the length of the unit;
* the **capacity** is per station, because the section changes;
* the **dead load** is per station for the same reason, and the two dead load
  stages are added before factoring because the rating equation takes one dead
  load effect and not two;
* the **influence line** is per station and is the expensive part, so it is
  built once and every vehicle is driven across it.

Stations are sampled rather than swept. The tenth points of each span are what a
rating sheet carries and are where the answer is, because the governing section
is either at a flange transition or near midspan and both land close to a tenth
point.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Final

from shearstud.analysis import deadload as dl
from shearstud.errors import InputError
from shearstud.loads import distribution as dist
from shearstud.loads import impact
from shearstud.loads.axles import AxleTrain
from shearstud.loads.continuous import continuous_moment
from shearstud.loads.influence import InfluenceLine, simple_moment
from shearstud.loads.live import LiveLoadCase, evaluate
from shearstud.rating import capacity as cap
from shearstud.rating import factors as fac
from shearstud.rating.rate import DeadLoad, RatingFactor, rate
from shearstud.store import assessment as asm
from shearstud.store import inventory
from shearstud.structure.girder import GirderLine
from shearstud.structure.record import Structure
from shearstud.structure.span import STATION_TOLERANCE_FT

#: How many stations are sampled along each span.
DEFAULT_STATIONS_PER_SPAN: Final[int] = 10

#: Lanes assumed loaded when the distribution factor is worked out. Two is the
#: governing case on every cross section in this inventory.
DEFAULT_LANES_LOADED: Final[int] = 2

#: Rating levels a run may be stored at, taken from the rating package rather
#: than written again, so that the two cannot drift apart.
RATING_LEVELS: Final[tuple[str, ...]] = fac.LEVELS

#: The load effect a moment run produces. Shear ratings go in under their own
#: name the day a shear run is written, and naming it here rather than passing
#: a bare string keeps that day from being a search for a string literal.
EFFECT_MOMENT: Final[str] = "moment"

#: How far either side of a pier the section is rated as a negative moment
#: section, as a fraction of the shorter adjoining span.
#:
#: The exact boundary is the point of contraflexure, which moves with the load
#: placement and is therefore not a station. A quarter of the span is where the
#: dead load contraflexure point sits on a balanced unit and is what a rating
#: sheet uses. Getting this wrong in the safe direction means rating a positive
#: moment section on its top flange with the deck ignored, which understates it;
#: getting it wrong the other way credits a deck that has cracked.
NEGATIVE_REGION_FRAC: Final[float] = 0.25


@dataclass(frozen=True, slots=True)
class RatingSettings:
    """Everything a rating needs that is not geometry."""

    steel_grade: str = "A36"
    member_condition: str = "good"
    redundancy: str = "redundant"
    adtt: float = 1000.0
    riding_surface: str = impact.SURFACE_MINOR
    barrier_klf: float = 0.45
    overlay_in: float = 0.0
    exterior_barrier_share_frac: float = 1.0
    stations_per_span: int = DEFAULT_STATIONS_PER_SPAN
    lanes_loaded: int = DEFAULT_LANES_LOADED

    def __post_init__(self) -> None:
        if self.stations_per_span < 2:
            raise InputError(f"{self.stations_per_span} stations is too few to find a maximum")
        if self.lanes_loaded < 1:
            raise InputError(f"{self.lanes_loaded} lanes loaded is not a load case")
        # Both of these raise with their own message if the word is unknown.
        cap.yield_stress_ksi(self.steel_grade)
        fac.condition_factor(self.member_condition)
        fac.system_factor(self.redundancy)


@dataclass(frozen=True, slots=True)
class StationRating:
    """One station's worth of ratings, with the workings kept."""

    girder_id: str
    station_ft: float
    distribution_factor: float
    capacity_kipft: float
    dead_component_kipft: float
    dead_surface_kipft: float
    ratings: tuple[RatingFactor, ...] = field(default_factory=tuple)

    @property
    def governing(self) -> RatingFactor:
        """The worst vehicle at this station."""
        if not self.ratings:
            raise InputError(f"{self.girder_id} at {self.station_ft} has no ratings")
        return min(self.ratings, key=lambda r: (r.value, r.vehicle))


def settings_for(path: Path | str, number: str, **overrides: object) -> RatingSettings:
    """A structure's rating settings, read off its record and then overridden.

    Four of the settings are agency judgement recorded against the structure
    and the rest are how this particular run is being done. Reading the first
    four here means a command cannot forget one, which is a mistake that
    produces a rating rather than an error: a girder rated as A36 when the
    drawing says A572-50 comes back low and plausible.

    An override of ``None`` is not an override. Click hands a missing option
    through as ``None`` and every command would otherwise have to strip those
    out itself.
    """
    policy = inventory.load_policy(path, number)
    fields: dict[str, object] = {
        "steel_grade": policy.steel_grade,
        "member_condition": policy.member_condition,
        "redundancy": policy.redundancy,
        "adtt": policy.adtt,
        "riding_surface": policy.riding_surface,
    }
    fields.update({name: value for name, value in overrides.items() if value is not None})
    return RatingSettings(**fields)  # type: ignore[arg-type]


def stations_for(structure: Structure, settings: RatingSettings) -> list[float]:
    """Global stations to rate at: the tenth points of every span."""
    out: list[float] = []
    for span in structure.spans:
        start_ft = structure.spans.to_global(span.index, 0.0)
        step_ft = span.length_ft / settings.stations_per_span
        for step in range(settings.stations_per_span + 1):
            station_ft = start_ft + step * step_ft
            if not out or station_ft > out[-1] + 1.0e-6:
                out.append(station_ft)
    return out


def is_negative_region(structure: Structure, global_station_ft: float) -> bool:
    """Whether a station is close enough to a pier to hog under live load.

    A simple span has no negative region at all, which is why this asks the
    span arrangement rather than the station. On a continuous unit the deck
    over the pier is in tension and cracked, so the section that resists there
    is the bare steel and the flange in compression is the bottom one.
    """
    if not structure.spans.continuous:
        return False
    for pier_ft in structure.spans.interior_support_stations_ft:
        index = structure.spans.span_index_at(pier_ft - STATION_TOLERANCE_FT)
        left_ft = structure.spans.spans[index].length_ft
        right_ft = structure.spans.spans[min(index + 1, structure.spans.span_count - 1)].length_ft
        reach_ft = NEGATIVE_REGION_FRAC * min(left_ft, right_ft)
        if abs(global_station_ft - pier_ft) <= reach_ft:
            return True
    return False


def capacity_at(
    structure: Structure, girder: GirderLine, station_ft: float, settings: RatingSettings
) -> cap.FlexuralCapacity:
    """The moment capacity in force at a station.

    Two different sections and two different fibres. In a positive moment
    region the deck works and the section can reach its plastic moment; over a
    pier the deck is cracked, the capacity comes off the bare steel, and the
    fibre in compression is the bottom flange rather than the top one. Rating
    a pier section as composite is a mistake that reads as a comfortable
    rating on the girder that is actually cracking.
    """
    section = girder.section_at(station_ft)
    if is_negative_region(structure, station_ft):
        return cap.flexural_capacity(section, settings.steel_grade, composite=False)
    return cap.flexural_capacity(
        section, settings.steel_grade, composite=True, fibre=cap.FIBRE_BOTTOM
    )


def influence_for(structure: Structure, global_station_ft: float) -> InfluenceLine:
    """Moment influence line at a station, continuity accounted for."""
    span_index, local_ft = structure.spans.to_local(global_station_ft)
    if structure.spans.continuous:
        return continuous_moment(list(structure.spans.lengths_ft), span_index, local_ft)
    return simple_moment(structure.spans.spans[span_index].length_ft, local_ft)


def distribution_for(structure: Structure, girder: GirderLine, settings: RatingSettings) -> float:
    """Moment distribution factor for one girder.

    The stiffness parameter is taken at midspan, where the section is the one
    the equation was fitted against. Taking it at a pier would read the heaviest
    section on the girder and overstate how much load it attracts.
    """
    midspan_ft = structure.length_ft / 2.0
    composite = girder.composite_at(midspan_ft)
    steel = composite.noncomposite
    deck_centre_in = composite.short_term.plate("deck").y_center_in
    stiffness = dist.GirderStiffness(
        inertia_in4=steel.inertia_in4,
        area_in2=steel.area_in2,
        eccentricity_in=deck_centre_in - steel.centroid_in,
        modular_ratio=8.0,
    )
    span_ft = max(structure.spans.lengths_ft)
    spacing_ft = girder.layout.average_spacing_ft
    if structure.girder_count < dist.MIN_BEAMS:
        # Outside the range the equations were fitted in. Statics, not an
        # extrapolation: hinge the deck over the first interior girder and
        # take the reaction, which is what the specification says to do and
        # what an engineer did before the equations existed.
        return dist.lever_rule_factor(
            spacing_ft, girder.layout.overhang_ft, lanes_loaded=settings.lanes_loaded
        )
    interior = dist.interior_moment(
        spacing_ft,
        span_ft,
        girder.layout.slab_thickness_in,
        stiffness,
        structure.girder_count,
        lanes_loaded=settings.lanes_loaded,
    )
    if not girder.is_exterior:
        return interior
    return interior * dist.exterior_correction_moment(girder.layout.overhang_ft - 1.0)


def dead_load_at(
    structure: Structure, girder: GirderLine, station_ft: float, settings: RatingSettings
) -> DeadLoad:
    """Dead load moment at a station, split the way the factors want it."""
    parts = dl.parts_for(
        girder,
        station_ft,
        barrier_klf=settings.barrier_klf,
        overlay_in=settings.overlay_in,
        exterior_share_frac=settings.exterior_barrier_share_frac if girder.is_exterior else 0.0,
        girder_count=structure.girder_count,
    )
    component_klf, surface_klf = dl.component_and_surface_klf(parts)
    span_ft = max(structure.spans.lengths_ft)
    return DeadLoad(
        component=dl.simple_span_moment_kipft(component_klf, span_ft),
        wearing_surface=dl.simple_span_moment_kipft(surface_klf, span_ft),
    )


def rate_station(
    structure: Structure,
    girder: GirderLine,
    station_ft: float,
    vehicles: Sequence[AxleTrain],
    settings: RatingSettings,
    *,
    limit_state: str = fac.STRENGTH_I,
    level: str = fac.OPERATING,
    legal: bool = True,
) -> StationRating:
    """Rate one station against a fleet."""
    if not vehicles:
        raise InputError("a rating run needs at least one vehicle")
    hogging = is_negative_region(structure, station_ft)
    flexural = capacity_at(structure, girder, station_ft, settings)
    factors = fac.resistance_factors(settings.member_condition, settings.redundancy)
    dead = dead_load_at(structure, girder, station_ft, settings)
    gamma_dc, gamma_dw = fac.dead_load_factors(limit_state, surface_measured=False)
    gamma_live = (
        fac.legal_live_factor(settings.adtt)
        if legal
        else fac.design_live_factor(limit_state, level)
    )
    allowance = (
        impact.legal_allowance_frac(settings.riding_surface)
        if legal
        else impact.allowance_frac(impact.STATE_STRENGTH)
    )
    factor = distribution_for(structure, girder, settings)
    case = LiveLoadCase(
        label=f"{girder.girder_id} at {station_ft:.1f}",
        influence=influence_for(structure, station_ft),
        distribution_factor=factor,
        allowance_frac=allowance,
    )
    ratings = []
    for vehicle in vehicles:
        # Over a pier the governing placement is the one that hogs most, which
        # is a different placement from the one that sags most and is found by
        # driving the same vehicle for the minimum rather than the maximum.
        effect = evaluate(case, vehicle, maximum=not hogging)
        ratings.append(
            rate(
                label=case.label,
                vehicle=vehicle.name,
                nominal_capacity=flexural.moment_kipft,
                factors=factors,
                dead=dead,
                gamma_dc=gamma_dc,
                gamma_dw=gamma_dw,
                live_effect=abs(effect.distributed),
                gamma_live=gamma_live,
                gross_weight_kip=vehicle.gross_kip,
            )
        )
    return StationRating(
        girder_id=girder.girder_id,
        station_ft=station_ft,
        distribution_factor=factor,
        capacity_kipft=flexural.moment_kipft * factors.product,
        dead_component_kipft=dead.component,
        dead_surface_kipft=dead.wearing_surface,
        ratings=tuple(ratings),
    )


def rate_structure(
    structure: Structure,
    vehicles: Sequence[AxleTrain],
    settings: RatingSettings | None = None,
    *,
    limit_state: str = fac.STRENGTH_I,
    level: str = fac.OPERATING,
    legal: bool = True,
) -> list[StationRating]:
    """Rate every girder at every sampled station.

    The abutment stations are skipped. Moment there is zero by definition and
    the rating comes out infinite, which is true and clutters every report.
    """
    used = settings or RatingSettings()
    out: list[StationRating] = []
    for girder in structure.girders:
        for station_ft in stations_for(structure, used):
            if station_ft <= 0.0 or station_ft >= structure.length_ft:
                continue
            out.append(
                rate_station(
                    structure,
                    girder,
                    station_ft,
                    vehicles,
                    used,
                    limit_state=limit_state,
                    level=level,
                    legal=legal,
                )
            )
    return out


def governing(results: Sequence[StationRating]) -> RatingFactor:
    """The worst rating anywhere on the structure."""
    if not results:
        raise InputError("nothing was rated")
    return min(
        (station.governing for station in results),
        key=lambda r: (r.value, r.label, r.vehicle),
    )


def store(
    path: Path | str,
    number: str,
    results: Sequence[StationRating],
    level: str,
    rated_on: date,
) -> int:
    """Write a run into the book, returning how many rows it wrote.

    Here rather than in the command that calls it because a run that is only
    stored by the command line is a run nothing else can store, and the
    programme ranking reads the book rather than the run. The date is passed in
    rather than taken from the clock so that a caller replaying a run can say
    when it happened.
    """
    if level not in RATING_LEVELS:
        raise InputError(f"unknown rating level {level!r}, expected one of {RATING_LEVELS}")
    written = 0
    for station in results:
        for factor in station.ratings:
            asm.save_rating(
                path,
                asm.StoredRating(
                    structure_number=number,
                    girder_id=station.girder_id,
                    station_ft=station.station_ft,
                    limit_state=fac.STRENGTH_I,
                    level=level,
                    vehicle=factor.vehicle,
                    effect=EFFECT_MOMENT,
                    capacity=factor.capacity,
                    factored_dead=factor.factored_dead,
                    factored_live=factor.factored_live,
                    rating_factor=factor.value,
                    gross_weight_kip=factor.gross_weight_kip,
                    rated_on=rated_on,
                ),
            )
            written += 1
    return written
