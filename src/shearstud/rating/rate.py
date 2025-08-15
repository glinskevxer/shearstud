"""The rating factor: capacity left over, divided by what the truck asks for.

One equation, and every term in it comes from somewhere else in this package:

    RF = (C - gamma_DC DC - gamma_DW DW) / (gamma_LL LL(1+IM))

C is the factored capacity, the dead loads are the structure's own weight and
its wearing surface, and the denominator is the distributed live load effect
with its dynamic allowance already in it.

A rating factor is a ratio, not a weight. Multiplying it by the gross weight of
the vehicle that produced it gives the tonnage the structure can carry, and that
is the number that goes on a sign. Doing that with the wrong vehicle is the
single most common way a posting comes out wrong, so
:meth:`RatingFactor.tonnage_kip` takes the weight off the result rather than
from a caller.

Dead load never gets a dynamic allowance and the denominator never gets one
applied twice. Both are structural properties of where the numbers come from
rather than checks, because the live load effect arrives already loaded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shearstud.errors import InputError, NotRatedError
from shearstud.rating.factors import ResistanceFactors

#: A rating factor at or above this is adequate. It is one by definition, and it
#: is named so that a report and a test agree on the comparison.
ADEQUATE = 1.0


@dataclass(frozen=True, slots=True)
class DeadLoad:
    """The two dead load components, kept apart because they factor apart."""

    component: float
    wearing_surface: float

    @property
    def total(self) -> float:
        """Unfactored dead load effect."""
        return self.component + self.wearing_surface

    def factored(self, gamma_dc: float, gamma_dw: float) -> float:
        """Dead load effect with each part carrying its own factor."""
        return gamma_dc * self.component + gamma_dw * self.wearing_surface


@dataclass(frozen=True, slots=True)
class RatingFactor:
    """One rating, with every term kept."""

    label: str
    vehicle: str
    capacity: float
    factored_dead: float
    factored_live: float
    gross_weight_kip: float

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise InputError("a rating needs a label")
        if self.gross_weight_kip <= 0.0:
            raise InputError(f"{self.label}: gross weight {self.gross_weight_kip} is not a weight")

    @property
    def available(self) -> float:
        """Capacity left after the dead load has taken its share."""
        return self.capacity - self.factored_dead

    @property
    def value(self) -> float:
        """The rating factor itself.

        Infinite when the live load effect is zero, which happens at a section
        no vehicle can load and is a real answer rather than a division to be
        guarded against.
        """
        if self.factored_live == 0.0:
            return math.inf
        return self.available / self.factored_live

    @property
    def is_adequate(self) -> bool:
        """True when the structure carries the vehicle."""
        return self.value >= ADEQUATE

    @property
    def dead_load_share(self) -> float:
        """How much of the capacity the dead load already used."""
        if self.capacity == 0.0:
            return 0.0
        return self.factored_dead / self.capacity

    def tonnage_kip(self) -> float:
        """Gross weight the structure can carry of this vehicle."""
        if math.isinf(self.value):
            return math.inf
        return self.value * self.gross_weight_kip

    def tonnage_tons(self) -> float:
        """The same number in short tons, which is what a sign carries."""
        return self.tonnage_kip() / 2.0


def rate(
    label: str,
    vehicle: str,
    nominal_capacity: float,
    factors: ResistanceFactors,
    dead: DeadLoad,
    gamma_dc: float,
    gamma_dw: float,
    live_effect: float,
    gamma_live: float,
    gross_weight_kip: float,
) -> RatingFactor:
    """Work the rating equation for one vehicle at one section."""
    if nominal_capacity <= 0.0:
        raise InputError(f"{label}: nominal capacity {nominal_capacity} is not a capacity")
    if gamma_live <= 0.0:
        raise InputError(f"{label}: live load factor {gamma_live} is not a factor")
    if gamma_dc <= 0.0 or gamma_dw <= 0.0:
        raise InputError(f"{label}: dead load factors must be positive")
    return RatingFactor(
        label=label,
        vehicle=vehicle,
        capacity=factors.product * nominal_capacity,
        factored_dead=dead.factored(gamma_dc, gamma_dw),
        factored_live=gamma_live * abs(live_effect),
        gross_weight_kip=gross_weight_kip,
    )


def governing(ratings: list[RatingFactor]) -> RatingFactor:
    """The worst rating in a set, ties broken by label."""
    if not ratings:
        raise NotRatedError("no ratings to choose between")
    return min(ratings, key=lambda r: (r.value, r.label))


def controlling_vehicle(ratings: list[RatingFactor]) -> str:
    """Which vehicle produced the worst rating."""
    return governing(ratings).vehicle


def all_adequate(ratings: list[RatingFactor]) -> bool:
    """True when every rating in the set clears one."""
    if not ratings:
        raise NotRatedError("no ratings to check")
    return all(r.is_adequate for r in ratings)
