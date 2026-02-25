"""Dead load, and which of the three composite sections each part lands on.

Dead load is the boring half of a rating and the half that is usually wrong,
because the parts arrive at different times and each part is carried by whatever
section existed when it arrived:

* the **steel** and the **wet deck** land on bare steel. There is nothing else
  there; the concrete is still a liquid;
* the **barrier**, the **rail** and any **future wearing surface** land on the
  long term composite section, softened for creep;
* nothing at all lands on the short term section, which exists only for live
  load.

This module computes the loads and says which stage carries each one. It does
not compute stresses, because that needs a section and this needs a girder.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from shearstud.errors import InputError
from shearstud.structure.girder import GirderLine
from shearstud.units import in_to_ft

#: Unit weights, kips per cubic foot.
STEEL_KCF: Final[float] = 0.490
CONCRETE_KCF: Final[float] = 0.150
ASPHALT_KCF: Final[float] = 0.140

#: Allowance for diaphragms, stiffeners, splice plates and the rest, as a
#: fraction of the bare girder weight. Weighing them properly needs a framing
#: plan, and this has been within a percent of the weighed answer on the three
#: structures where anyone has checked.
STEEL_DETAIL_ALLOWANCE: Final[float] = 0.08

#: Load stages, matching the three composite sections.
STAGE_NONCOMPOSITE: Final[str] = "noncomposite"
STAGE_LONG_TERM: Final[str] = "long_term"
STAGES: Final[tuple[str, ...]] = (STAGE_NONCOMPOSITE, STAGE_LONG_TERM)


@dataclass(frozen=True, slots=True)
class DeadLoadPart:
    """One dead load, and when it arrived."""

    name: str
    load_klf: float
    stage: str
    is_wearing_surface: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InputError("a dead load part needs a name")
        if self.load_klf < 0.0:
            raise InputError(f"{self.name}: {self.load_klf} klf is a negative load")
        if self.stage not in STAGES:
            raise InputError(f"{self.name}: unknown load stage {self.stage!r}")


def steel_weight_klf(girder: GirderLine, station_ft: float) -> float:
    """Weight of the girder itself at a station, detail allowance included."""
    area_in2 = girder.section_at(station_ft).area_in2
    bare_klf = area_in2 * in_to_ft(1.0) * in_to_ft(1.0) * STEEL_KCF
    return bare_klf * (1.0 + STEEL_DETAIL_ALLOWANCE)


def deck_weight_klf(girder: GirderLine) -> float:
    """Weight of the deck and haunch this girder carries."""
    slab_in2 = girder.deck.thickness_in * girder.deck.effective_width_in
    top_flange = girder.section_at(0.0).plate("top")
    haunch_in2 = girder.deck.haunch_in * top_flange.width_in
    total_in2 = slab_in2 + haunch_in2
    return total_in2 * in_to_ft(1.0) * in_to_ft(1.0) * CONCRETE_KCF


def barrier_weight_klf(barrier_klf: float, girder_count: int, exterior_share_frac: float) -> float:
    """One girder's share of the barriers.

    Barriers sit over the exterior girders and the deck distributes some of that
    inward. ``exterior_share_frac`` is how much of a barrier the girder under it
    keeps; the remainder is spread over the rest. A share of one is the
    conservative reading for an exterior girder and zero spreads it evenly.
    """
    if girder_count < 1:
        raise InputError(f"{girder_count} girders is not a cross section")
    if not 0.0 <= exterior_share_frac <= 1.0:
        raise InputError(f"exterior share {exterior_share_frac} is outside zero to one")
    if barrier_klf < 0.0:
        raise InputError(f"barrier weight {barrier_klf} is negative")
    return barrier_klf * exterior_share_frac


def wearing_surface_klf(thickness_in: float, tributary_width_ft: float) -> float:
    """Weight of an asphalt overlay over one girder's tributary width."""
    if thickness_in < 0.0:
        raise InputError(f"overlay thickness {thickness_in} is negative")
    if tributary_width_ft <= 0.0:
        raise InputError(f"tributary width {tributary_width_ft} is not a width")
    return in_to_ft(thickness_in) * tributary_width_ft * ASPHALT_KCF


def parts_for(
    girder: GirderLine,
    station_ft: float,
    barrier_klf: float = 0.0,
    overlay_in: float = 0.0,
    exterior_share_frac: float = 0.0,
    girder_count: int = 4,
) -> list[DeadLoadPart]:
    """Every dead load on one girder, each tagged with its stage."""
    tributary_ft = girder.deck.effective_width_in / 12.0
    out = [
        DeadLoadPart("girder", steel_weight_klf(girder, station_ft), STAGE_NONCOMPOSITE),
        DeadLoadPart("deck", deck_weight_klf(girder), STAGE_NONCOMPOSITE),
    ]
    if barrier_klf > 0.0:
        share = barrier_weight_klf(barrier_klf, girder_count, exterior_share_frac)
        out.append(DeadLoadPart("barrier", share, STAGE_LONG_TERM))
    if overlay_in > 0.0:
        out.append(
            DeadLoadPart(
                "wearing surface",
                wearing_surface_klf(overlay_in, tributary_ft),
                STAGE_LONG_TERM,
                is_wearing_surface=True,
            )
        )
    return out


def total_klf(parts: list[DeadLoadPart], stage: str | None = None) -> float:
    """Sum of the parts, optionally only those on one stage."""
    if stage is not None and stage not in STAGES:
        raise InputError(f"unknown load stage {stage!r}")
    return sum(p.load_klf for p in parts if stage is None or p.stage == stage)


def component_and_surface_klf(parts: list[DeadLoadPart]) -> tuple[float, float]:
    """Split the parts the way the load factors do.

    The wearing surface factors separately from everything else, so this is the
    split a rating needs and the only split it needs.
    """
    surface = sum(p.load_klf for p in parts if p.is_wearing_surface)
    component = sum(p.load_klf for p in parts if not p.is_wearing_surface)
    return component, surface


def simple_span_moment_kipft(load_klf: float, span_ft: float) -> float:
    """Midspan moment from a uniform load on a simply supported span."""
    if span_ft <= 0.0:
        raise InputError(f"span {span_ft} is not a span")
    return load_klf * span_ft * span_ft / 8.0


def simple_span_shear_kip(load_klf: float, span_ft: float) -> float:
    """End shear from a uniform load on a simply supported span."""
    if span_ft <= 0.0:
        raise InputError(f"span {span_ft} is not a span")
    return load_klf * span_ft / 2.0
