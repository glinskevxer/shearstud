"""Dynamic load allowance, and the one load it is never applied to.

A truck bouncing on an uneven deck delivers more than its static weight, and the
specification handles that with a flat percentage rather than a dynamic
analysis. Three things about it are easy to get wrong and all three are settled
here:

* the design lane load gets no dynamic allowance, ever. It is a notional
  distributed load, not a vehicle, and adding thirty three percent to it is a
  mistake that survives review because the number still looks plausible;
* the fatigue allowance is not the strength one. Fatigue is driven by the
  everyday truck on a deck in its everyday condition, and the specification
  gives it fifteen percent against thirty three;
* a legal load rating may use a reduced allowance when the approach and deck
  have actually been looked at. That is a field observation, not an assumption,
  so the surface condition has to be stated.
"""

from __future__ import annotations

from typing import Final

from shearstud.errors import InputError

#: Limit states that carry a dynamic allowance.
STATE_STRENGTH: Final[str] = "strength"
STATE_SERVICE: Final[str] = "service"
STATE_FATIGUE: Final[str] = "fatigue"
STATE_DECK_JOINT: Final[str] = "deck_joint"
STATES: Final[tuple[str, ...]] = (STATE_STRENGTH, STATE_SERVICE, STATE_FATIGUE, STATE_DECK_JOINT)

#: Riding surface condition, as an inspector records it.
SURFACE_SMOOTH: Final[str] = "smooth"
SURFACE_MINOR: Final[str] = "minor"
SURFACE_ROUGH: Final[str] = "rough"
SURFACES: Final[tuple[str, ...]] = (SURFACE_SMOOTH, SURFACE_MINOR, SURFACE_ROUGH)

#: Base allowances by limit state, as a fraction of the static effect.
BASE_ALLOWANCE: Final[dict[str, float]] = {
    STATE_STRENGTH: 0.33,
    STATE_SERVICE: 0.33,
    STATE_FATIGUE: 0.15,
    STATE_DECK_JOINT: 0.75,
}

#: Reduced allowances a legal load rating may use when the surface has been
#: inspected, AASHTO MBE 6A.4.4.3.
LEGAL_ALLOWANCE: Final[dict[str, float]] = {
    SURFACE_SMOOTH: 0.10,
    SURFACE_MINOR: 0.20,
    SURFACE_ROUGH: 0.33,
}

#: Depth of fill above a buried structure at which the allowance disappears.
BURIAL_CUTOFF_FT: Final[float] = 8.0


def allowance_frac(limit_state: str) -> float:
    """Dynamic allowance for a limit state, as a fraction."""
    if limit_state not in BASE_ALLOWANCE:
        raise InputError(f"unknown limit state {limit_state!r}, expected one of {STATES}")
    return BASE_ALLOWANCE[limit_state]


def legal_allowance_frac(surface: str) -> float:
    """Reduced allowance for a legal load rating on an inspected surface."""
    if surface not in LEGAL_ALLOWANCE:
        raise InputError(f"unknown riding surface {surface!r}, expected one of {SURFACES}")
    return LEGAL_ALLOWANCE[surface]


def buried_allowance_frac(limit_state: str, fill_ft: float) -> float:
    """Allowance for a structure with fill over it.

    The allowance falls off linearly with depth of fill and is gone by the
    cutoff, because at that depth the fill has damped everything the truck does.
    """
    if fill_ft < 0.0:
        raise InputError(f"fill depth {fill_ft} is negative")
    base = allowance_frac(limit_state)
    if fill_ft >= BURIAL_CUTOFF_FT:
        return 0.0
    return base * (1.0 - fill_ft / BURIAL_CUTOFF_FT)


def apply(static_effect: float, allowance: float) -> float:
    """Multiply a static vehicle effect by one plus the allowance."""
    if allowance < 0.0:
        raise InputError(f"dynamic allowance {allowance} is negative")
    return static_effect * (1.0 + allowance)


def combine_truck_and_lane(truck_effect: float, lane_effect: float, allowance: float) -> float:
    """Truck plus lane, with the allowance on the truck only.

    This function exists so that no caller ever has to remember which of the two
    the allowance lands on. It is the only place in the package where a truck
    effect and a lane effect are added together.
    """
    return apply(truck_effect, allowance) + lane_effect
