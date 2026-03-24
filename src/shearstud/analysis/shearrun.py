"""Rating a structure in shear, which is a different run and not a variation.

Four things change from the moment run and every one of them has caught
somebody out.

**Where it is rated.** The moment run skips the abutments, because moment there
is zero and the rating comes back infinite. Shear is at its largest at the
abutment. A shear run that reuses the moment run's station list drops exactly
the station that governs, and it drops it silently.

**What resists it.** The web, not the section. Shear capacity does not care
which flange is heavier and it does not care whether the deck is composite; it
cares about the web's depth over its thickness and whether anybody welded
stiffeners on. On the 1962 stringers in this inventory nobody did.

**How it is distributed.** AASHTO's shear distribution factor is a different
equation from the moment one, with no stiffness term in it at all. Using the
moment factor because it is to hand is wrong in both directions depending on
the spacing, and it is wrong by enough to move a posting.

**How the live effect is read.** The shear influence line has a jump at the
section, so the value there depends on which side you ask from. The convention
here is that the section is rated for the larger of the two, because the web
does not know which side the load engineer was standing on.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Final

from shearstud.analysis import deadload as dl
from shearstud.analysis.ratingrun import RatingSettings, stations_for
from shearstud.errors import InputError
from shearstud.loads import distribution as dist
from shearstud.loads import impact
from shearstud.loads.axles import AxleTrain
from shearstud.loads.continuous import continuous_shear
from shearstud.loads.influence import InfluenceLine, simple_shear
from shearstud.loads.live import LiveLoadCase, evaluate
from shearstud.rating import capacity as cap
from shearstud.rating import factors as fac
from shearstud.rating.rate import DeadLoad, RatingFactor, rate
from shearstud.store import assessment as asm
from shearstud.structure.girder import GirderLine
from shearstud.structure.record import Structure

#: The load effect these ratings carry in the book.
EFFECT_SHEAR: Final[str] = "shear"

#: How far off an abutment the end station is taken, in feet. Exactly at the
#: support the influence line is discontinuous and the dead load shear is at a
#: point no member exists at; a foot in is where a rating sheet reads it and is
#: what the end panel actually carries.
END_OFFSET_FT: Final[float] = 1.0


@dataclass(frozen=True, slots=True)
class ShearRating:
    """One station's shear ratings, with the workings kept."""

    girder_id: str
    station_ft: float
    distribution_factor: float
    capacity_kip: float
    dead_component_kip: float
    dead_surface_kip: float
    web_slenderness: float
    ratings: tuple[RatingFactor, ...] = field(default_factory=tuple)

    @property
    def governing(self) -> RatingFactor:
        """The worst vehicle at this station."""
        if not self.ratings:
            raise InputError(f"{self.girder_id} at {self.station_ft} has no shear ratings")
        return min(self.ratings, key=lambda r: (r.value, r.vehicle))

    @property
    def is_at_an_end(self) -> bool:
        """True when this is one of the end stations shear is largest at."""
        return self.station_ft <= END_OFFSET_FT


def shear_stations(structure: Structure, settings: RatingSettings) -> list[float]:
    """Stations to rate shear at: the moment stations plus both ends.

    The ends are the reason this exists. Reusing the moment run's list drops
    the two stations where shear governs.
    """
    out = [
        station
        for station in stations_for(structure, settings)
        if END_OFFSET_FT < station < structure.length_ft - END_OFFSET_FT
    ]
    return sorted({END_OFFSET_FT, *out, structure.length_ft - END_OFFSET_FT})


def influence_for(structure: Structure, global_station_ft: float) -> InfluenceLine:
    """Shear influence line at a station, continuity accounted for."""
    span_index, local_ft = structure.spans.to_local(global_station_ft)
    if structure.spans.continuous:
        return continuous_shear(list(structure.spans.lengths_ft), span_index, local_ft)
    return simple_shear(structure.spans.spans[span_index].length_ft, local_ft)


def distribution_for(girder: GirderLine, settings: RatingSettings) -> float:
    """Shear distribution factor for one girder.

    No stiffness term, which is the whole difference from the moment factor.
    AASHTO's shear equation is fitted on the spacing alone, so this does not
    need the structure at all, and its moment counterpart does. Reaching for
    the moment factor because it is already computed is the mistake this
    function exists to make impossible.
    """
    spacing_ft = girder.layout.average_spacing_ft
    interior = dist.interior_shear(spacing_ft, lanes_loaded=settings.lanes_loaded)
    if not girder.is_exterior:
        return interior
    return interior * dist.exterior_correction_shear(girder.layout.overhang_ft - 1.0)


def dead_load_at(
    structure: Structure, girder: GirderLine, station_ft: float, settings: RatingSettings
) -> DeadLoad:
    """Dead load shear at a station, split the way the load factors want it."""
    parts = dl.parts_for(
        girder,
        station_ft,
        barrier_klf=settings.barrier_klf,
        overlay_in=settings.overlay_in,
        exterior_share_frac=settings.exterior_barrier_share_frac if girder.is_exterior else 0.0,
        girder_count=structure.girder_count,
    )
    component_klf, surface_klf = dl.component_and_surface_klf(parts)
    span_index, local_ft = structure.spans.to_local(station_ft)
    span_ft = structure.spans.spans[span_index].length_ft
    return DeadLoad(
        component=abs(dl.simple_span_shear_at_kip(component_klf, span_ft, local_ft)),
        wearing_surface=abs(dl.simple_span_shear_at_kip(surface_klf, span_ft, local_ft)),
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
) -> ShearRating:
    """Rate one station in shear against a fleet."""
    if not vehicles:
        raise InputError("a shear run needs at least one vehicle")
    section = girder.section_at(station_ft)
    nominal_kip = cap.shear_capacity_kip(section, settings.steel_grade)
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
    factor = distribution_for(girder, settings)
    case = LiveLoadCase(
        label=f"{girder.girder_id} at {station_ft:.1f}",
        influence=influence_for(structure, station_ft),
        distribution_factor=factor,
        allowance_frac=allowance,
    )
    ratings = []
    for vehicle in vehicles:
        # Both directions, because the line jumps at the section and the web
        # carries whichever is larger.
        largest = max(
            evaluate(case, vehicle, maximum=True).distributed,
            abs(evaluate(case, vehicle, maximum=False).distributed),
        )
        ratings.append(
            rate(
                label=case.label,
                vehicle=vehicle.name,
                nominal_capacity=nominal_kip,
                factors=factors,
                dead=dead,
                gamma_dc=gamma_dc,
                gamma_dw=gamma_dw,
                live_effect=largest,
                gamma_live=gamma_live,
                gross_weight_kip=vehicle.gross_kip,
            )
        )
    return ShearRating(
        girder_id=girder.girder_id,
        station_ft=station_ft,
        distribution_factor=factor,
        capacity_kip=nominal_kip * factors.product,
        dead_component_kip=dead.component,
        dead_surface_kip=dead.wearing_surface,
        web_slenderness=cap.web_slenderness(section),
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
) -> list[ShearRating]:
    """Rate every girder in shear at every station, ends included."""
    used = settings or RatingSettings()
    out: list[ShearRating] = []
    for girder in structure.girders:
        for station_ft in shear_stations(structure, used):
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


def governing(results: Sequence[ShearRating]) -> RatingFactor:
    """The worst shear rating anywhere on the structure."""
    if not results:
        raise InputError("nothing was rated in shear")
    return min(
        (station.governing for station in results),
        key=lambda r: (r.value, r.label, r.vehicle),
    )


def store(
    path: Path | str,
    number: str,
    results: Sequence[ShearRating],
    level: str,
    rated_on: date,
) -> int:
    """Write a shear run into the book, returning how many rows it wrote."""
    if level not in fac.LEVELS:
        raise InputError(f"unknown rating level {level!r}, expected one of {fac.LEVELS}")
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
                    effect=EFFECT_SHEAR,
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
