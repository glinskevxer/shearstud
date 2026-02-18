"""How long until this structure gets looked at again.

The routine inspection interval is twenty four months and has been for a long
time. What the regulation added is the two ways off it: down to twelve months
when something about the structure says come back sooner, and out to forty eight
months when everything about it says there is no need to. There is nothing in
between. An interval of thirty months is not a shorter forty eight, it is a
number nobody will accept, so the answer here is always one of three.

The shape of the rule is what makes it worth writing down rather than
remembering. The shorteners are independent and any one of them fires: a poor
deck shortens the interval whatever the fatigue life says, and a detail five
years from the end shortens it whatever the deck looks like. The extension is
the opposite. It needs every condition at once, and a single one missing leaves
the interval at twenty four rather than moving it partway.

So a structure can be a long way from the shorteners and still not qualify for
the extension, which is the case the office gets wrong. Being fine is not the
same as being eligible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from shearstud.errors import InputError

#: The interval a structure gets when nothing is said about it.
ROUTINE_MONTHS: Final[int] = 24

#: The interval a shortener drops it to.
SHORT_MONTHS: Final[int] = 12

#: The longest interval the regulation allows, and only on a clean sheet.
EXTENDED_MONTHS: Final[int] = 48

#: Every interval this office will write on a form.
ALLOWED_MONTHS: Final[tuple[int, ...]] = (SHORT_MONTHS, ROUTINE_MONTHS, EXTENDED_MONTHS)

#: The National Bridge Inventory condition scale, worst to best.
MIN_CONDITION_RATING: Final[int] = 0
MAX_CONDITION_RATING: Final[int] = 9

#: At or below this rating a component is in poor condition.
POOR_CONDITION_RATING: Final[int] = 4

#: The rating an extension needs on every component.
EXTENSION_CONDITION_RATING: Final[int] = 7

#: Remaining fatigue life below this shortens the interval.
SHORTEN_YEARS: Final[float] = 5.0

#: Remaining fatigue life below this blocks the extension without shortening.
EXTENSION_YEARS: Final[float] = 20.0

#: How the answer is described on the form.
DRIVER_CONDITION: Final[str] = "condition"
DRIVER_POSTING: Final[str] = "posting"
DRIVER_FATIGUE: Final[str] = "fatigue"
DRIVER_REDUNDANCY: Final[str] = "redundancy"
DRIVER_ROUTINE: Final[str] = "routine"
DRIVER_EXTENSION: Final[str] = "extension"

#: Days in a month, for turning an interval into a date. The regulation counts
#: in months and the database stores a date, and this is where the two meet.
DAYS_PER_MONTH: Final[float] = 30.4375


@dataclass(frozen=True, slots=True)
class StructureState:
    """Everything the interval rule asks about a structure."""

    lowest_condition_rating: int
    is_posted: bool
    has_nonredundant_members: bool
    fatigue_life_years: float

    def __post_init__(self) -> None:
        if not MIN_CONDITION_RATING <= self.lowest_condition_rating <= MAX_CONDITION_RATING:
            raise InputError(
                f"condition rating {self.lowest_condition_rating} is outside "
                f"{MIN_CONDITION_RATING} to {MAX_CONDITION_RATING}"
            )
        if self.fatigue_life_years < 0.0:
            raise InputError(f"a fatigue life of {self.fatigue_life_years} years is not a life")

    @property
    def is_poor(self) -> bool:
        """True when a component is in poor condition or worse."""
        return self.lowest_condition_rating <= POOR_CONDITION_RATING

    @property
    def fatigue_is_pressing(self) -> bool:
        """True when the fatigue life is short enough to shorten the interval."""
        return self.fatigue_life_years < SHORTEN_YEARS

    @property
    def fatigue_allows_extension(self) -> bool:
        """True when there is enough life left not to have to come back early."""
        return self.fatigue_life_years >= EXTENSION_YEARS


@dataclass(frozen=True, slots=True)
class Decision:
    """The interval, and the one thing that set it."""

    months: int
    driver: str
    reason: str

    def __post_init__(self) -> None:
        if self.months not in ALLOWED_MONTHS:
            raise InputError(f"{self.months} months is not an interval this office writes down")

    @property
    def is_shortened(self) -> bool:
        """True when something pulled the interval in from routine."""
        return self.months < ROUTINE_MONTHS

    @property
    def is_extended(self) -> bool:
        """True when the structure qualified for the long interval."""
        return self.months > ROUTINE_MONTHS

    def next_due(self, last_inspected: date) -> date:
        """When the next inspection falls due."""
        return last_inspected + timedelta(days=round(self.months * DAYS_PER_MONTH))

    def is_overdue(self, last_inspected: date, today: date) -> bool:
        """True when the due date has already gone past."""
        return today > self.next_due(last_inspected)


def shorteners(state: StructureState) -> list[str]:
    """Every reason to come back inside a year, in the order they are read."""
    found: list[str] = []
    if state.is_poor:
        found.append(DRIVER_CONDITION)
    if state.is_posted:
        found.append(DRIVER_POSTING)
    if state.fatigue_is_pressing:
        found.append(DRIVER_FATIGUE)
    return found


def extension_blockers(state: StructureState) -> list[str]:
    """Every condition the extension needs that this structure does not meet."""
    found: list[str] = []
    if state.lowest_condition_rating < EXTENSION_CONDITION_RATING:
        found.append(DRIVER_CONDITION)
    if state.is_posted:
        found.append(DRIVER_POSTING)
    if state.has_nonredundant_members:
        found.append(DRIVER_REDUNDANCY)
    if not state.fatigue_allows_extension:
        found.append(DRIVER_FATIGUE)
    return found


def decide(state: StructureState) -> Decision:
    """The interval this structure gets, and why it got it."""
    short = shorteners(state)
    if short:
        return Decision(
            months=SHORT_MONTHS,
            driver=short[0],
            reason=f"shortened by {', '.join(short)}",
        )
    blocked = extension_blockers(state)
    if not blocked:
        return Decision(
            months=EXTENDED_MONTHS,
            driver=DRIVER_EXTENSION,
            reason="every condition for the extension is met",
        )
    return Decision(
        months=ROUTINE_MONTHS,
        driver=blocked[0],
        reason=f"routine, extension blocked by {', '.join(blocked)}",
    )


def months_for(state: StructureState) -> int:
    """Just the number, for a caller that does not want the reasoning."""
    return decide(state).months


def soonest(decisions: list[Decision], last_inspected: date) -> date:
    """The earliest due date across several decisions.

    A structure carries more than one inspection type and the office works to
    whichever comes first.
    """
    if not decisions:
        raise InputError("no decisions to compare")
    return min(decision.next_due(last_inspected) for decision in decisions)
