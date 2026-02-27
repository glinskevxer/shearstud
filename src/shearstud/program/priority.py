"""Which structures get looked at first, and why they cannot share one score.

Every bridge management system anyone has ever bought computes a priority
number, and every office that has used one has watched a sound high traffic
structure outrank a posted one because the traffic term was large enough. The
number is not wrong. Adding a consequence term to a condition term is what
produces it, and there is no set of weights that stops it happening, because the
two terms are answers to different questions.

So this does not produce a score. It produces a band, and the band decides what
is then measured. A structure that cannot carry the legal loads is in the first
band whatever its traffic is; within that band traffic decides the order,
because among structures that all need the same thing, the one carrying the most
traffic should get it first. A structure with three years of fatigue life is in
the second band whatever its condition rating says, and inside that band the
order is by life rather than by traffic, because the thing being rationed there
is time before a crack rather than money.

The bands are read in order and the first one that fits wins. That is the whole
rule. It means a structure is never in two bands, it means the reason for its
position is a sentence rather than a weighting, and it means two people ranking
the same inventory get the same list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from shearstud.errors import InputError
from shearstud.program.interval import StructureState

#: Cannot carry the legal loads. Nothing else is asked.
BAND_RESTRICTED: Final[str] = "restricted"

#: Carrying the loads, but not for many more years.
BAND_RETROFIT: Final[str] = "retrofit"

#: Sound enough to carry, worn enough to be worth spending on now.
BAND_PRESERVE: Final[str] = "preserve"

#: Nothing to do but come back on schedule.
BAND_MONITOR: Final[str] = "monitor"

#: The order the bands are read in, which is also the order of the worklist.
BANDS: Final[tuple[str, ...]] = (BAND_RESTRICTED, BAND_RETROFIT, BAND_PRESERVE, BAND_MONITOR)

#: A rating factor below this cannot carry the load it was rated for.
RESTRICTED_RATING_FACTOR: Final[float] = 1.0

#: Fatigue life below this many years puts a structure in the retrofit band.
RETROFIT_YEARS: Final[float] = 5.0

#: Condition at or below this, with life left, is worth preserving now.
PRESERVE_CONDITION_RATING: Final[int] = 6

#: What each band is measured on once a structure is in it.
BAND_MEASURE: Final[dict[str, str]] = {
    BAND_RESTRICTED: "traffic carried and the detour if it closes",
    BAND_RETROFIT: "years of fatigue life left",
    BAND_PRESERVE: "condition rating, worst first",
    BAND_MONITOR: "when the next inspection falls due",
}


@dataclass(frozen=True, slots=True)
class Candidate:
    """One structure, as the ranking sees it."""

    number: str
    state: StructureState
    rating_factor: float
    daily_traffic: int
    detour_mi: float

    def __post_init__(self) -> None:
        if not self.number.strip():
            raise InputError("a candidate needs a structure number")
        if self.rating_factor < 0.0:
            raise InputError(f"{self.number}: rating factor {self.rating_factor} is negative")
        if self.daily_traffic < 0:
            raise InputError(f"{self.number}: traffic {self.daily_traffic} is negative")
        if self.detour_mi < 0.0:
            raise InputError(f"{self.number}: a detour of {self.detour_mi} miles is not a detour")

    @property
    def is_restricted(self) -> bool:
        """True when the structure cannot carry what it was rated for."""
        return self.rating_factor < RESTRICTED_RATING_FACTOR

    @property
    def user_cost_index(self) -> float:
        """Traffic times detour, which is what a closure would cost the public.

        Deliberately not a dollar figure. It is compared against other members
        of the same band and against nothing else, and giving it units would
        invite exactly the cross band arithmetic this module refuses to do.
        """
        return self.daily_traffic * self.detour_mi


def band_of(candidate: Candidate) -> str:
    """Which band a structure falls in. The first that fits wins."""
    if candidate.is_restricted or candidate.state.is_posted:
        return BAND_RESTRICTED
    if candidate.state.fatigue_life_years < RETROFIT_YEARS:
        return BAND_RETROFIT
    if candidate.state.lowest_condition_rating <= PRESERVE_CONDITION_RATING:
        return BAND_PRESERVE
    return BAND_MONITOR


def reason_for(candidate: Candidate) -> str:
    """A sentence saying why the structure is where it is."""
    band = band_of(candidate)
    if band == BAND_RESTRICTED:
        if candidate.is_restricted:
            return f"rating factor {candidate.rating_factor:.2f} is below one"
        return "already posted"
    if band == BAND_RETROFIT:
        return f"{candidate.state.fatigue_life_years:.1f} years of fatigue life left"
    if band == BAND_PRESERVE:
        return f"condition rating {candidate.state.lowest_condition_rating}"
    return "carrying the loads with life and condition to spare"


def _order_key(candidate: Candidate) -> tuple[float, str]:
    """What the structure's own band measures it on, smallest first."""
    band = band_of(candidate)
    if band == BAND_RESTRICTED:
        return (-candidate.user_cost_index, candidate.number)
    if band == BAND_RETROFIT:
        return (candidate.state.fatigue_life_years, candidate.number)
    if band == BAND_PRESERVE:
        return (candidate.state.lowest_condition_rating, candidate.number)
    return (-candidate.user_cost_index, candidate.number)


def in_band(candidates: list[Candidate], band: str) -> list[Candidate]:
    """Everything in one band, in that band's own order."""
    if band not in BANDS:
        raise InputError(f"unknown band {band!r}")
    found = [c for c in candidates if band_of(c) == band]
    return sorted(found, key=_order_key)


def worklist(candidates: list[Candidate]) -> list[Candidate]:
    """Every structure, band by band, ordered inside each band."""
    out: list[Candidate] = []
    for band in BANDS:
        out.extend(in_band(candidates, band))
    return out


def counts(candidates: list[Candidate]) -> dict[str, int]:
    """How many structures are in each band, including the empty ones."""
    out = dict.fromkeys(BANDS, 0)
    for candidate in candidates:
        out[band_of(candidate)] += 1
    return out


def top(candidates: list[Candidate], limit: int) -> list[Candidate]:
    """The first few off the worklist."""
    if limit < 1:
        raise InputError(f"a list of {limit} structures is not a list")
    return worklist(candidates)[:limit]
