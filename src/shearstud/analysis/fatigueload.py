"""The computed stress range at a detail nobody has put a gauge on.

Every fatigue evaluation in this package so far starts from a measured
spectrum, which means it reaches the one detail in twelve that has a gauge on
it. The other eleven are the ones this module is for: their stress range is
computed from the fatigue truck rather than measured, and the answer is worse
than a measurement and much better than nothing.

Four things make the fatigue load different from the rating load and all four
are easy to carry across by accident.

**One truck, one lane.** Fatigue is a repeated event and two trucks side by side
is not a repeated event, so the distribution factor is the one lane one with the
multiple presence factor taken back out. Using the two lane factor overstates
the range by about a fifth on a typical spacing.

**The rear axle spacing is fixed.** The design truck's variable gap governs
different effects at its two ends and is a parameter everywhere else in this
package. For fatigue the specification fixes it at thirty feet.

**The dynamic allowance is fifteen per cent**, not the thirty three the strength
check uses. Fatigue is driven by the ordinary truck on an ordinary day, not by
the one that hits the bad joint.

**The section is the short term composite one**, at every station including over
a pier. The deck is uncracked under a fatigue load because the load is small,
which is the opposite of the assumption a strength check makes there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from shearstud.analysis.ratingrun import RatingSettings, influence_for
from shearstud.analysis.ratingrun import distribution_for as moment_distribution
from shearstud.errors import InputError
from shearstud.loads import distribution as dist
from shearstud.loads import impact, vehicles
from shearstud.loads.axles import AxleTrain
from shearstud.loads.live import LiveLoadCase, evaluate
from shearstud.structure.detail import FIBRE_BOTTOM, FIBRE_TOP, FatigueDetail
from shearstud.structure.girder import GirderLine
from shearstud.structure.record import Structure
from shearstud.units import kipft_to_kipin

#: The rear axle gap the fatigue truck is specified at, in feet. Fixed, unlike
#: the rating truck's, which is a parameter at both ends of its range.
FATIGUE_REAR_GAP_FT: Final[float] = 30.0

#: Lanes loaded for fatigue. One, because fatigue is a repeated event and two
#: trucks side by side is not one.
FATIGUE_LANES_LOADED: Final[int] = 1

#: A web detail is taken at the fibre nearest it, which on these girders is the
#: bottom flange, because the web details in this inventory are the stiffener
#: terminations at the bottom of the web.
WEB_DETAIL_FIBRE: Final[str] = FIBRE_BOTTOM


@dataclass(frozen=True, slots=True)
class ComputedRange:
    """A stress range worked out rather than measured, with its workings."""

    detail_id: str
    station_ft: float
    fibre: str
    distribution_factor: float
    moment_range_kipft: float
    section_modulus_in3: float
    range_ksi: float

    @property
    def is_computed(self) -> bool:
        """Always true, and it is on the record so a report can say so.

        A computed range and a measured one are different pieces of evidence
        and a report that shows them in one column without saying which is
        which is a report somebody will read the wrong way.
        """
        return True


def fatigue_truck() -> AxleTrain:
    """The design truck at the fixed fatigue rear axle spacing."""
    return vehicles.design_truck(FATIGUE_REAR_GAP_FT)


def distribution_for(structure: Structure, girder: GirderLine) -> float:
    """The one lane moment factor with the presence factor taken back out.

    The moment equation and not the shear one, because a stress range at a
    flange is a moment effect. It is the same function the rating run uses,
    asked for one lane, so a change to the distribution model reaches both.

    AASHTO's table factors include the multiple presence factor, and for one
    lane that is 1.2. Fatigue is one truck on the bridge, so the factor comes
    back out. Leaving it in overstates every computed range by a fifth.
    """
    settings = RatingSettings(lanes_loaded=FATIGUE_LANES_LOADED)
    raw = moment_distribution(structure, girder, settings)
    return raw / dist.presence_factor(FATIGUE_LANES_LOADED)


def fibre_of(detail: FatigueDetail) -> str:
    """Which fibre a detail's stress range is taken at."""
    if detail.fibre == FIBRE_TOP:
        return FIBRE_TOP
    return WEB_DETAIL_FIBRE


def section_modulus_for(girder: GirderLine, detail: FatigueDetail) -> float:
    """The short term composite section modulus at a detail's fibre.

    Short term at every station, over a pier included. A fatigue load is small
    enough that the deck stays uncracked, which is the opposite of what a
    strength check assumes there.
    """
    composite = girder.composite_at(detail.station_ft)
    section = composite.short_term
    if fibre_of(detail) == FIBRE_TOP:
        return section.section_modulus_top_in3
    return section.section_modulus_bottom_in3


def stress_range(structure: Structure, girder: GirderLine, detail: FatigueDetail) -> ComputedRange:
    """The stress range one pass of the fatigue truck puts at a detail.

    Nothing here takes rating settings. Every input is either specified by the
    fatigue provisions or read off the structure, so there is nothing for a
    caller to choose, and an argument a caller can pass but cannot usefully
    vary is an argument somebody will pass the wrong thing to.
    """
    if detail.station_ft > structure.length_ft:
        raise InputError(
            f"{detail.detail_id} is at {detail.station_ft} ft on a {structure.length_ft} ft unit"
        )
    factor = distribution_for(structure, girder)
    case = LiveLoadCase(
        label=detail.detail_id,
        influence=influence_for(structure, detail.station_ft),
        distribution_factor=factor,
        allowance_frac=impact.allowance_frac(impact.STATE_FATIGUE),
        lane_load_klf=0.0,
    )
    truck = fatigue_truck()
    largest = evaluate(case, truck, maximum=True).distributed
    smallest = evaluate(case, truck, maximum=False).distributed
    moment_range_kipft = largest - smallest
    modulus_in3 = section_modulus_for(girder, detail)
    return ComputedRange(
        detail_id=detail.detail_id,
        station_ft=detail.station_ft,
        fibre=fibre_of(detail),
        distribution_factor=factor,
        moment_range_kipft=moment_range_kipft,
        section_modulus_in3=modulus_in3,
        range_ksi=kipft_to_kipin(moment_range_kipft) / modulus_in3,
    )


def ranges_for(structure: Structure) -> list[ComputedRange]:
    """Every detail on the structure, worst range first."""
    out: list[ComputedRange] = []
    for girder in structure.girders:
        for detail in girder.details:
            out.append(stress_range(structure, girder, detail))
    return sorted(out, key=lambda found: (-found.range_ksi, found.detail_id))
