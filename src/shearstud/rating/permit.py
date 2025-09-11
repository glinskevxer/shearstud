"""Permit ratings: one heavy load, crossing once, under stated conditions.

A permit rating is not a legal load rating with a bigger truck in it. The whole
point of a permit is that the conditions of the crossing are controlled, and the
live load factor drops as the control tightens:

* a **routine** permit is a standing authorisation for a vehicle that mixes with
  ordinary traffic whenever it likes, so it carries almost the same factor a
  legal load does;
* a **single trip** permit is one crossing on a known day. If it crosses mixed
  with traffic the factor is lower than routine; if the bridge is cleared and
  the vehicle is escorted down the centre line at a crawl, lower again, because
  there is then exactly one vehicle on the structure and it is where the
  analysis put it.

The conditions are therefore inputs to the factor, and this module refuses a
combination that does not make sense rather than picking the nearest row: an
escorted routine permit is not a thing, because nobody escorts a vehicle that
crosses unannounced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from shearstud.errors import InputError

#: Permit kinds.
ROUTINE: Final[str] = "routine"
SINGLE_TRIP: Final[str] = "single_trip"
KINDS: Final[tuple[str, ...]] = (ROUTINE, SINGLE_TRIP)

#: How the crossing is controlled.
MIXED: Final[str] = "mixed"
ESCORTED: Final[str] = "escorted"
CONTROLS: Final[tuple[str, ...]] = (MIXED, ESCORTED)

#: Live load factors, AASHTO MBE Table 6A.4.5.4.2a-1 collapsed to the two
#: conditions this agency actually issues.
PERMIT_LIVE_FACTORS: Final[dict[tuple[str, str], float]] = {
    (ROUTINE, MIXED): 1.40,
    (SINGLE_TRIP, MIXED): 1.20,
    (SINGLE_TRIP, ESCORTED): 1.10,
}

#: Routine permits get the same traffic dependent floor a legal load does, so a
#: heavily trafficked structure does not get the benefit of the lower factor.
ROUTINE_HIGH_ADTT: Final[float] = 5000.0
ROUTINE_HIGH_ADTT_FACTOR: Final[float] = 1.50

#: An escorted crossing is slow enough that the dynamic allowance drops.
ESCORTED_ALLOWANCE_FRAC: Final[float] = 0.0

#: A mixed crossing takes the ordinary allowance.
MIXED_ALLOWANCE_FRAC: Final[float] = 0.33


@dataclass(frozen=True, slots=True)
class PermitConditions:
    """The conditions the permit is issued under."""

    kind: str
    control: str
    adtt: float

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise InputError(f"unknown permit kind {self.kind!r}, expected one of {KINDS}")
        if self.control not in CONTROLS:
            raise InputError(f"unknown crossing control {self.control!r}")
        if self.adtt < 0.0:
            raise InputError(f"truck traffic {self.adtt} is negative")
        if self.kind == ROUTINE and self.control == ESCORTED:
            raise InputError("a routine permit crosses unannounced and cannot be escorted")

    @property
    def live_factor(self) -> float:
        """Live load factor for these conditions."""
        base = PERMIT_LIVE_FACTORS[(self.kind, self.control)]
        if self.kind == ROUTINE and self.adtt >= ROUTINE_HIGH_ADTT:
            return ROUTINE_HIGH_ADTT_FACTOR
        return base

    @property
    def allowance_frac(self) -> float:
        """Dynamic allowance for the crossing."""
        return ESCORTED_ALLOWANCE_FRAC if self.control == ESCORTED else MIXED_ALLOWANCE_FRAC

    @property
    def lanes_loaded(self) -> int:
        """How many lanes the analysis puts load in.

        An escorted crossing has the bridge to itself, so one lane. A mixed
        crossing has to allow for a legal load alongside.
        """
        return 1 if self.control == ESCORTED else 2

    @property
    def is_controlled(self) -> bool:
        """True when the crossing conditions are enforced on the day."""
        return self.control == ESCORTED


def live_factor(kind: str, control: str, adtt: float) -> float:
    """Live load factor from the three conditions, without building the record."""
    return PermitConditions(kind=kind, control=control, adtt=adtt).live_factor


def is_issuable(rating_factor: float) -> bool:
    """Whether a permit can be issued on this rating.

    A permit rating of one means the structure carries the vehicle under the
    stated conditions, and nothing about a permit allows going below that.
    """
    return rating_factor >= 1.0


def margin(rating_factor: float) -> float:
    """How much room the permit has, as a fraction of the vehicle."""
    return rating_factor - 1.0


def tightest_control_needed(rating_by_control: dict[str, float], kind: str = SINGLE_TRIP) -> str:
    """The loosest control that still lets the permit be issued.

    Called with the ratings computed under each control in turn. Returns the
    first control, from loosest to tightest, that clears one. Escorting a
    vehicle costs the haulier real money, so an agency that always answers
    "escorted" is charging for margin it does not need.
    """
    if kind not in KINDS:
        raise InputError(f"unknown permit kind {kind!r}")
    order = [MIXED, ESCORTED] if kind == SINGLE_TRIP else [MIXED]
    for control in order:
        if control not in rating_by_control:
            raise InputError(f"no rating supplied for a {control} crossing")
        if is_issuable(rating_by_control[control]):
            return control
    raise InputError("the vehicle does not rate under any control this permit allows")
