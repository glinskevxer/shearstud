"""The whole fatigue evaluation for one detail, end to end.

Everything the fatigue package does separately is assembled here, in the order
an evaluation report is written in:

1. the measured spectrum, extrapolated from however long the campaign ran to a
   year of traffic;
2. the damage that year does at the detail's category;
3. the infinite life question, which if it comes back yes stops the calculation;
4. the remaining life, with the traffic growing.

Step one is where the campaign length matters and where the most common mistake
lives. A two week campaign scaled to a year by multiplying by twenty six is only
right if those two weeks were typical, and a campaign run in one season on a
route with a harvest peak is not. The extrapolation therefore takes a seasonal
factor, defaulting to one, and the report says what it was.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from shearstud.errors import InputError
from shearstud.fatigue import damage as dmg
from shearstud.fatigue import life as lf
from shearstud.fatigue.categories import DetailCategory
from shearstud.signals.spectrum import Spectrum
from shearstud.units import STEEL_E_KSI

#: Days in the year every extrapolation here uses.
DAYS_PER_YEAR: Final[float] = 365.0

#: A campaign shorter than this cannot see a weekly traffic cycle and its
#: extrapolation is a guess wearing a number.
MIN_CAMPAIGN_DAYS: Final[float] = 7.0

#: Remaining life below this many years puts the detail on the list for a
#: retrofit rather than another inspection.
RETROFIT_YEARS: Final[float] = 5.0

#: Remaining life below this many years is worth a shorter inspection interval.
WATCH_YEARS: Final[float] = 20.0


@dataclass(frozen=True, slots=True)
class Campaign:
    """How long the gauge was recording, and how typical it was."""

    days: float
    seasonal_factor: float = 1.0

    def __post_init__(self) -> None:
        if self.days < MIN_CAMPAIGN_DAYS:
            raise InputError(
                f"a {self.days} day campaign is shorter than the {MIN_CAMPAIGN_DAYS} "
                f"days it takes to see a week of traffic"
            )
        if self.seasonal_factor <= 0.0:
            raise InputError(f"seasonal factor {self.seasonal_factor} is not a factor")

    @property
    def annual_scale(self) -> float:
        """What the campaign's cycle counts multiply by to reach a year."""
        return DAYS_PER_YEAR / self.days * self.seasonal_factor

    @property
    def is_typical(self) -> bool:
        """True when no seasonal correction was applied."""
        return self.seasonal_factor == 1.0


@dataclass(frozen=True, slots=True)
class Evaluation:
    """What a fatigue evaluation concluded, with the workings kept."""

    detail_id: str
    detail_category: str
    campaign_days: float
    annual_cycles: float
    effective_range_ksi: float
    largest_range_ksi: float
    infinite_life: bool
    damage_per_first_year: float
    years_remaining: float

    @property
    def needs_retrofit(self) -> bool:
        """True when the detail is close enough to failure to fix rather than
        watch."""
        return self.years_remaining < RETROFIT_YEARS

    @property
    def needs_watching(self) -> bool:
        """True when the detail wants a shorter inspection interval."""
        return RETROFIT_YEARS <= self.years_remaining < WATCH_YEARS

    @property
    def is_comfortable(self) -> bool:
        """True when the detail is not the reason to come back."""
        return self.years_remaining >= WATCH_YEARS

    @property
    def verdict(self) -> str:
        """One word for the summary column."""
        if self.needs_retrofit:
            return "retrofit"
        if self.needs_watching:
            return "watch"
        return "comfortable"


def annual_spectrum(measured: Spectrum, campaign: Campaign) -> Spectrum:
    """Scale a campaign's spectrum up to a year of traffic."""
    return measured.scaled_count(campaign.annual_scale)


def evaluate(
    detail_id: str,
    measured: Spectrum,
    campaign: Campaign,
    detail: DetailCategory,
    traffic: lf.TrafficModel,
    modulus_ksi: float = STEEL_E_KSI,
    damage_already_done: float = 0.0,
) -> Evaluation:
    """Run the four steps and package the answer."""
    if not detail_id.strip():
        raise InputError("an evaluation needs a detail id")
    yearly = annual_spectrum(measured, campaign)
    result = dmg.accumulate(yearly, detail, modulus_ksi)
    years = lf.years_remaining(result.damage, traffic, damage_already_done)
    return Evaluation(
        detail_id=detail_id,
        detail_category=detail.name,
        campaign_days=campaign.days,
        annual_cycles=yearly.total_count,
        effective_range_ksi=result.effective_range_ksi,
        largest_range_ksi=result.largest_range_ksi,
        infinite_life=result.infinite_life,
        damage_per_first_year=result.damage,
        years_remaining=years,
    )


def worst_of(evaluations: list[Evaluation]) -> Evaluation:
    """The detail with the least life left, ties broken by id."""
    if not evaluations:
        raise InputError("no evaluations to choose between")
    return min(evaluations, key=lambda e: (e.years_remaining, e.detail_id))


def needing_attention(evaluations: list[Evaluation]) -> list[Evaluation]:
    """Every detail that is not comfortable, worst first."""
    found = [e for e in evaluations if not e.is_comfortable]
    return sorted(found, key=lambda e: (e.years_remaining, e.detail_id))


def structure_life_years(evaluations: list[Evaluation]) -> float:
    """The life of the structure's fatigue behaviour, which is its worst detail.

    Infinite when every detail is infinite life, which is the answer a modern
    welded structure with no cover plates on it usually gives.
    """
    if not evaluations:
        raise InputError("no evaluations to summarise")
    return min(e.years_remaining for e in evaluations)


def is_indefinite(evaluations: list[Evaluation]) -> bool:
    """True when no detail on the structure accumulates damage."""
    return math.isinf(structure_life_years(evaluations))
