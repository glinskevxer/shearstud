"""Load and resistance factors for a load and resistance factor rating.

The factors are where the rating's judgement lives. Everything else in this
package is arithmetic on measurements; these numbers say how much margin the
agency wants, and they change with what the vehicle is, how much traffic there
is, what condition the member is in and whether the structure has anywhere to
shed load to.

Two rules here are easy to lose and both are enforced rather than documented:

* the product of the condition factor and the system factor has a floor. A poor
  member on a non redundant structure would otherwise stack two reductions and
  land below anything the specification contemplates;
* the live load factor for a legal load is interpolated on truck traffic, not
  picked from a bracket. The published table gives three points and says to
  interpolate, and rounding to the nearest one is worth five percent on a
  rating factor.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from shearstud.errors import InputError

#: Limit states a rating is taken at.
STRENGTH_I: Final[str] = "strength_i"
SERVICE_II: Final[str] = "service_ii"
LIMIT_STATES: Final[tuple[str, ...]] = (STRENGTH_I, SERVICE_II)

#: Rating levels.
INVENTORY: Final[str] = "inventory"
OPERATING: Final[str] = "operating"
LEVELS: Final[tuple[str, ...]] = (INVENTORY, OPERATING)

#: Dead load factors at Strength I. The wearing surface carries more because its
#: thickness is guessed more often than it is measured.
GAMMA_DC_STRENGTH: Final[float] = 1.25
GAMMA_DW_STRENGTH: Final[float] = 1.50

#: The wearing surface factor drops to this once its thickness has been
#: measured in the field rather than taken off the plans.
GAMMA_DW_MEASURED: Final[float] = 1.25

#: Dead load factors at Service II, where nothing is factored up.
GAMMA_DC_SERVICE: Final[float] = 1.00
GAMMA_DW_SERVICE: Final[float] = 1.00

#: Live load factors for the design load, by level and limit state.
DESIGN_LIVE_FACTORS: Final[dict[tuple[str, str], float]] = {
    (STRENGTH_I, INVENTORY): 1.75,
    (STRENGTH_I, OPERATING): 1.35,
    (SERVICE_II, INVENTORY): 1.30,
    (SERVICE_II, OPERATING): 1.00,
}

#: Legal load live factors against truck traffic, AASHTO MBE Table 6A.4.4.2.3a-1.
LEGAL_LIVE_POINTS: Final[tuple[tuple[float, float], ...]] = (
    (100.0, 1.40),
    (1000.0, 1.65),
    (5000.0, 1.80),
)

#: Condition factors by the member's own condition, MBE Table 6A.4.2.3-1.
CONDITION_FACTORS: Final[dict[str, float]] = {"good": 1.00, "fair": 0.95, "poor": 0.85}

#: Floor on the product of condition and system factors.
MIN_CONDITION_SYSTEM_PRODUCT: Final[float] = 0.85

#: System factors by how much redundancy the structure has.
SYSTEM_FACTORS: Final[dict[str, float]] = {
    "redundant": 1.00,
    "limited": 0.90,
    "non_redundant": 0.85,
}


def dead_load_factors(limit_state: str, *, surface_measured: bool = False) -> tuple[float, float]:
    """Component and wearing surface dead load factors."""
    if limit_state == STRENGTH_I:
        dw = GAMMA_DW_MEASURED if surface_measured else GAMMA_DW_STRENGTH
        return GAMMA_DC_STRENGTH, dw
    if limit_state == SERVICE_II:
        return GAMMA_DC_SERVICE, GAMMA_DW_SERVICE
    raise InputError(f"unknown limit state {limit_state!r}, expected one of {LIMIT_STATES}")


def design_live_factor(limit_state: str, level: str) -> float:
    """Live load factor for a design load rating."""
    if limit_state not in LIMIT_STATES:
        raise InputError(f"unknown limit state {limit_state!r}")
    if level not in LEVELS:
        raise InputError(f"unknown rating level {level!r}, expected one of {LEVELS}")
    return DESIGN_LIVE_FACTORS[(limit_state, level)]


def legal_live_factor(adtt: float) -> float:
    """Live load factor for a legal load, interpolated on truck traffic."""
    if adtt < 0.0:
        raise InputError(f"truck traffic {adtt} is negative")
    points = LEGAL_LIVE_POINTS
    if adtt <= points[0][0]:
        return points[0][1]
    if adtt >= points[-1][0]:
        return points[-1][1]
    for (low_adtt, low_factor), (high_adtt, high_factor) in pairwise(points):
        if low_adtt <= adtt <= high_adtt:
            span = high_adtt - low_adtt
            return low_factor + (high_factor - low_factor) * (adtt - low_adtt) / span
    raise InputError(f"could not place {adtt} on the legal load factor table")


def condition_factor(condition: str) -> float:
    """Condition factor for the member being rated."""
    key = condition.strip().lower()
    if key not in CONDITION_FACTORS:
        raise InputError(f"unknown member condition {condition!r}")
    return CONDITION_FACTORS[key]


def system_factor(redundancy: str) -> float:
    """System factor for the structure's redundancy."""
    key = redundancy.strip().lower()
    if key not in SYSTEM_FACTORS:
        raise InputError(f"unknown redundancy {redundancy!r}")
    return SYSTEM_FACTORS[key]


@dataclass(frozen=True, slots=True)
class ResistanceFactors:
    """The three factors that multiply the nominal resistance."""

    condition: float
    system: float
    resistance: float

    def __post_init__(self) -> None:
        for name, value in (
            ("condition", self.condition),
            ("system", self.system),
            ("resistance", self.resistance),
        ):
            if not 0.0 < value <= 1.0:
                raise InputError(f"{name} factor {value} is outside zero to one")

    @property
    def product(self) -> float:
        """All three multiplied, with the floor on the first two applied."""
        pair = max(self.condition * self.system, MIN_CONDITION_SYSTEM_PRODUCT)
        return pair * self.resistance

    @property
    def is_floored(self) -> bool:
        """True when the floor on condition times system actually bit."""
        return self.condition * self.system < MIN_CONDITION_SYSTEM_PRODUCT


def resistance_factors(
    condition: str, redundancy: str, resistance: float = 1.00
) -> ResistanceFactors:
    """Build the factor set from the words a structure record holds."""
    return ResistanceFactors(
        condition=condition_factor(condition),
        system=system_factor(redundancy),
        resistance=resistance,
    )
