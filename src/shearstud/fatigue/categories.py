"""Fatigue detail categories, their constants, and the S-N curve.

Eight categories, from a plain rolled surface at A down to a cover plate end on
a thick flange at E prime. Each carries two numbers: the detail constant that
sets the sloping part of the S-N curve, and the constant amplitude fatigue
threshold below which a cycle does no damage at all.

The spread is the thing to hold on to. E prime has a detail constant sixty four
times smaller than A and a threshold nine times lower, so the same stress range
that is harmless at a rolled edge is a finite life problem at a cover plate end.
Getting the category wrong is worth more than any other single input in this
package.

The two limit states are both here and they answer different questions. Fatigue
I asks whether the detail lasts forever and compares against the threshold.
Fatigue II asks how long it lasts and rides the sloping curve. A detail that
fails Fatigue I has not failed; it has a finite life, and the finite life is
what Fatigue II is for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from shearstud.errors import ConfigError

#: Slope of the S-N curve in log space. Every category shares it.
CURVE_EXPONENT: Final[float] = 3.0


@dataclass(frozen=True, slots=True)
class DetailCategory:
    """One row of AASHTO LRFD Table 6.6.1.2.5-1."""

    name: str
    constant_a: float
    threshold_ksi: float
    example: str

    def cycles_to_failure(self, range_ksi: float) -> float:
        """Cycles the sloping curve gives for a stress range.

        Below the threshold this returns infinity, which is the honest answer
        for a constant amplitude problem and the wrong one for a variable
        amplitude one. Variable amplitude work goes through
        :func:`shearstud.fatigue.damage`, which knows about the shallower
        second slope.
        """
        if range_ksi <= 0.0:
            raise ConfigError(f"{self.name}: stress range {range_ksi} is not a range")
        if range_ksi < self.threshold_ksi:
            return math.inf
        return self.constant_a / math.pow(range_ksi, CURVE_EXPONENT)

    def range_for_cycles_ksi(self, cycles: float) -> float:
        """Stress range the sloping curve allows for a given life."""
        if cycles <= 0.0:
            raise ConfigError(f"{self.name}: {cycles} cycles is not a life")
        return math.pow(self.constant_a / cycles, 1.0 / CURVE_EXPONENT)

    def resistance_ksi(self, cycles: float, *, infinite_life: bool) -> float:
        """Nominal fatigue resistance under one of the two limit states."""
        if infinite_life:
            return self.threshold_ksi
        return self.range_for_cycles_ksi(cycles)

    def is_infinite_life(self, range_ksi: float) -> bool:
        """True when a constant amplitude range at this detail never fails."""
        return range_ksi < self.threshold_ksi


_TABLE: Final[dict[str, DetailCategory]] = {
    "A": DetailCategory("A", 250.0e8, 24.0, "plain rolled or cleaned surface, no attachment"),
    "B": DetailCategory("B", 120.0e8, 16.0, "full penetration groove weld ground flush"),
    "B'": DetailCategory("B'", 61.0e8, 12.0, "longitudinal fillet welded built up member"),
    "C": DetailCategory("C", 44.0e8, 10.0, "transverse stiffener weld to flange or web"),
    "C'": DetailCategory("C'", 44.0e8, 12.0, "transverse stiffener weld, base metal at the toe"),
    "D": DetailCategory("D", 22.0e8, 7.0, "attachment between two and four inches long"),
    "E": DetailCategory("E", 11.0e8, 4.5, "cover plate end on a flange under an inch thick"),
    "E'": DetailCategory("E'", 3.9e8, 2.6, "cover plate end on a thicker flange, no end weld"),
}

#: Category names in order of decreasing resistance, which is the order a
#: report lists them and the order the letters already imply.
NAMES: Final[tuple[str, ...]] = ("A", "B", "B'", "C", "C'", "D", "E", "E'")


def category(name: str) -> DetailCategory:
    """One category by name. Accepts a prime written as an apostrophe or a P."""
    key = name.strip().upper().replace("PRIME", "'").replace("P", "'")
    if key not in _TABLE:
        raise ConfigError(f"unknown detail category {name!r}, expected one of {NAMES}")
    return _TABLE[key]


def categories() -> list[DetailCategory]:
    """Every category, strongest first."""
    return [_TABLE[name] for name in NAMES]


def weakest_of(names: list[str]) -> DetailCategory:
    """The governing category from a set of details at one section.

    Two details at the same section see the same stress range, so the weaker one
    decides. This is used where a stiffener weld and a cover plate end land
    within a few inches of each other.
    """
    if not names:
        raise ConfigError("no detail categories to choose between")
    return min((category(name) for name in names), key=lambda c: c.constant_a)
