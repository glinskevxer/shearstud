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
from shearstud.structure.girder import GirderLine
from shearstud.structure.record import Structure

#: How many stations are sampled along each span.
DEFAULT_STATIONS_PER_SPAN: Final[int] = 10

#: Lanes assumed loaded when the distribution factor is worked out. Two is the
#: governing case on every cross section in this inventory.
DEFAULT_LANES_LOADED: Final[int] = 2


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
    flexural = cap.flexural_capacity(
        girder.section_at(station_ft), settings.steel_grade, composite=True
    )
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
        effect = evaluate(case, vehicle)
        ratings.append(
            rate(
                label=case.label,
                vehicle=vehicle.name,
                nominal_capacity=flexural.moment_kipft,
                factors=factors,
                dead=dead,
                gamma_dc=gamma_dc,
                gamma_dw=gamma_dw,
                live_effect=effect.distributed,
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
