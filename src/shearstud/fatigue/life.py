"""Turning damage per year into years, with traffic that grows.

Everything up to here is per cycle. This module is where cycles become calendar
time, and it needs three things a strain record cannot tell it: how many trucks
a day cross the structure, how many cycles each truck puts into the detail, and
how fast the traffic is growing.

Growth is compounded, not averaged, and the difference is not small. Two percent
a year over a forty year projection is a factor of 2.2 on the last year's
traffic, and a remaining life computed at today's volume overstates the answer
by about a quarter. The closed form is used rather than a year by year loop
because the loop tempts a caller to stop it early and read a partial sum as an
answer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from shearstud.errors import InputError

#: Fraction of trucks in the single lane carrying the most, AASHTO LRFD Table
#: 3.6.1.4.2-1, by number of lanes available to trucks.
LANE_FRACTIONS: Final[dict[int, float]] = {1: 1.00, 2: 0.85}

#: Three lanes or more all take this one.
LANE_FRACTION_MANY: Final[float] = 0.80

#: Span at which a simple span goes from two cycles per truck to one, because a
#: shorter span sees the axle groups as separate events.
SHORT_SPAN_FT: Final[float] = 40.0

#: Days in the year used for every annual extrapolation here.
DAYS_PER_YEAR: Final[float] = 365.0


def adtt_single_lane(adtt: float, lanes_available: int) -> float:
    """Average daily truck traffic in the single most heavily loaded lane."""
    if adtt < 0.0:
        raise InputError(f"truck traffic {adtt} is negative")
    if lanes_available < 1:
        raise InputError(f"{lanes_available} lanes is not a roadway")
    fraction = LANE_FRACTIONS.get(lanes_available, LANE_FRACTION_MANY)
    return adtt * fraction


def cycles_per_truck(span_ft: float, *, continuous: bool, near_support: bool = False) -> float:
    """How many stress cycles one truck passage puts into a detail.

    A short span sees each axle group as its own event, so one truck is two
    cycles. A detail near an interior support of a continuous unit sees the
    truck in both adjoining spans, which is worth an extra half cycle.
    """
    if span_ft <= 0.0:
        raise InputError(f"span {span_ft} is not a span")
    if near_support and not continuous:
        raise InputError("a simple span has no interior support to be near")
    base = 2.0 if span_ft <= SHORT_SPAN_FT else 1.0
    if near_support:
        return base + 0.5
    return base


@dataclass(frozen=True, slots=True)
class TrafficModel:
    """What the traffic does, as a rating needs it."""

    adtt: float
    lanes_available: int
    growth_pct_per_yr: float
    cycles_per_passage: float

    def __post_init__(self) -> None:
        if self.adtt < 0.0:
            raise InputError(f"truck traffic {self.adtt} is negative")
        if self.lanes_available < 1:
            raise InputError(f"{self.lanes_available} lanes is not a roadway")
        if self.growth_pct_per_yr < -100.0:
            raise InputError(f"growth {self.growth_pct_per_yr} percent removes more than all of it")
        if self.cycles_per_passage <= 0.0:
            raise InputError(f"{self.cycles_per_passage} cycles per truck is not a count")

    @property
    def growth_frac_per_yr(self) -> float:
        """Growth as a fraction rather than a percentage."""
        return self.growth_pct_per_yr / 100.0

    @property
    def adtt_single_lane(self) -> float:
        """Trucks a day in the lane that carries the most."""
        return adtt_single_lane(self.adtt, self.lanes_available)

    def cycles_in_first_year(self) -> float:
        """Cycles the detail sees in year one, at today's traffic."""
        return self.adtt_single_lane * self.cycles_per_passage * DAYS_PER_YEAR

    def cycles_in_year(self, year: int) -> float:
        """Cycles in a given year, counting the first year as year zero."""
        if year < 0:
            raise InputError(f"year {year} is before the projection starts")
        return self.cycles_in_first_year() * math.pow(1.0 + self.growth_frac_per_yr, year)

    def cycles_through(self, years: float) -> float:
        """Total cycles over a whole number of years of growing traffic."""
        if years < 0.0:
            raise InputError(f"{years} years is not a projection")
        growth = self.growth_frac_per_yr
        first = self.cycles_in_first_year()
        if abs(growth) < 1.0e-12:
            return first * years
        return first * (math.pow(1.0 + growth, years) - 1.0) / growth


@dataclass(frozen=True, slots=True)
class RemainingLife:
    """How much life is left at one detail, and what it was worked out from."""

    detail_category: str
    damage_already_done: float
    damage_per_first_year: float
    years_remaining: float

    @property
    def is_expired(self) -> bool:
        """True when the calculation says the life is already used up."""
        return self.years_remaining <= 0.0

    @property
    def is_indefinite(self) -> bool:
        """True when nothing accumulates and the life never runs out."""
        return math.isinf(self.years_remaining)


def years_remaining(
    damage_per_first_year: float, traffic: TrafficModel, damage_already_done: float = 0.0
) -> float:
    """Solve the compounded damage sum for the year it reaches one.

    ``damage_per_first_year`` is the damage the detail takes in the first year
    at today's traffic. Later years scale with the traffic growth, so the total
    is a geometric series and the answer is a logarithm rather than a loop.
    """
    if damage_per_first_year < 0.0:
        raise InputError(f"damage per year {damage_per_first_year} is negative")
    if not 0.0 <= damage_already_done <= 1.0:
        raise InputError(f"damage already done {damage_already_done} is outside zero to one")
    capacity = 1.0 - damage_already_done
    if damage_per_first_year == 0.0:
        return math.inf
    if capacity <= 0.0:
        return 0.0
    growth = traffic.growth_frac_per_yr
    if abs(growth) < 1.0e-12:
        return capacity / damage_per_first_year
    ratio = 1.0 + capacity * growth / damage_per_first_year
    if ratio <= 0.0:
        return math.inf
    return math.log(ratio) / math.log(1.0 + growth)


def remaining_life(
    detail_category: str,
    damage_per_first_year: float,
    traffic: TrafficModel,
    damage_already_done: float = 0.0,
) -> RemainingLife:
    """Package the answer with the inputs that produced it."""
    return RemainingLife(
        detail_category=detail_category,
        damage_already_done=damage_already_done,
        damage_per_first_year=damage_per_first_year,
        years_remaining=years_remaining(damage_per_first_year, traffic, damage_already_done),
    )
