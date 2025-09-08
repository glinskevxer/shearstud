"""Turning rating factors into a posting sign.

A posting is not a rating. A rating is a ratio; a posting is a weight in tons on
a sign at the end of the bridge, and getting from one to the other involves
three decisions that are policy rather than mechanics:

* **which vehicles are on the sign.** This agency posts three: a single unit, a
  semi and a combination, because those are the three silhouettes on the
  standard sign blank. A structure that fails only for the six axle combination
  gets one number on the sign, not three;
* **rounding.** Always down, and to the nearest ton. Rounding a 24.6 up to 25
  puts half a ton of load on the structure that the rating did not allow;
* **when to post at all.** A rating factor at or a shade above one does not get
  posted. Below the threshold it does, and below the closure threshold the
  structure comes out of service rather than getting a very low sign.

None of the three is derivable from the rating, which is why they are constants
here with the reasoning attached rather than arguments a caller passes in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from shearstud.errors import InputError
from shearstud.rating.rate import RatingFactor

#: Rating factor at or above which nothing is posted.
POSTING_THRESHOLD: Final[float] = 1.0

#: Below this the structure is closed rather than posted. A sign this low is
#: not enforceable and the traffic that ignores it is the traffic that matters.
CLOSURE_THRESHOLD: Final[float] = 0.3

#: Lowest weight the agency will put on a sign, in tons.
MIN_POSTED_TONS: Final[float] = 3.0

#: The three silhouettes on the standard sign blank, and the catalogue vehicle
#: each one is rated with.
SIGN_VEHICLES: Final[dict[str, str]] = {
    "single_unit": "TYPE3",
    "semi": "TYPE3S2",
    "combination": "TYPE3-3",
}

#: What the posting decision came out as.
OPEN: Final[str] = "open"
POSTED: Final[str] = "posted"
CLOSED: Final[str] = "closed"
OUTCOMES: Final[tuple[str, ...]] = (OPEN, POSTED, CLOSED)


def posted_tons(rating: RatingFactor) -> float:
    """Weight to put on the sign for one vehicle, rounded down to the ton."""
    if rating.value >= POSTING_THRESHOLD:
        return math.inf
    return math.floor(rating.tonnage_tons())


@dataclass(frozen=True, slots=True)
class SignLine:
    """One silhouette on the sign, and what it carries."""

    silhouette: str
    vehicle: str
    rating_factor: float
    tons: float

    @property
    def is_posted(self) -> bool:
        """True when this line actually appears on the sign."""
        return math.isfinite(self.tons)

    @property
    def is_below_the_minimum(self) -> bool:
        """True when the arithmetic gives a weight too low to sign."""
        return self.is_posted and self.tons < MIN_POSTED_TONS


@dataclass(frozen=True, slots=True)
class PostingDecision:
    """What the structure gets: nothing, a sign, or a barricade."""

    outcome: str
    lines: tuple[SignLine, ...]
    governing_factor: float

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise InputError(f"unknown posting outcome {self.outcome!r}")

    @property
    def posted_lines(self) -> tuple[SignLine, ...]:
        """Only the silhouettes that carry a weight."""
        return tuple(line for line in self.lines if line.is_posted)

    @property
    def lowest_tons(self) -> float:
        """The smallest weight on the sign, or infinity when nothing is posted."""
        posted = self.posted_lines
        if not posted:
            return math.inf
        return min(line.tons for line in posted)


def decide(ratings: dict[str, RatingFactor]) -> PostingDecision:
    """Work a set of legal load ratings into a posting decision.

    ``ratings`` is keyed by silhouette, and every silhouette on the sign blank
    has to be present. A missing one is refused rather than skipped, because a
    sign with a blank line reads as no limit for that vehicle.
    """
    missing = sorted(set(SIGN_VEHICLES) - set(ratings))
    if missing:
        raise InputError(f"no rating for the {missing[0]} silhouette")
    lines = tuple(
        SignLine(
            silhouette=silhouette,
            vehicle=ratings[silhouette].vehicle,
            rating_factor=ratings[silhouette].value,
            tons=posted_tons(ratings[silhouette]),
        )
        for silhouette in SIGN_VEHICLES
    )
    governing = min(line.rating_factor for line in lines)
    if governing < CLOSURE_THRESHOLD:
        outcome = CLOSED
    elif governing < POSTING_THRESHOLD:
        outcome = POSTED
    else:
        outcome = OPEN
    return PostingDecision(outcome=outcome, lines=lines, governing_factor=governing)


def sign_text(decision: PostingDecision) -> list[str]:
    """The lines a sign shop would letter, in silhouette order.

    An open structure gets an empty list rather than a line saying so, because
    there is no sign to make.
    """
    if decision.outcome == CLOSED:
        return ["BRIDGE CLOSED"]
    out = []
    for line in decision.lines:
        if not line.is_posted:
            continue
        label = line.silhouette.replace("_", " ").upper()
        out.append(f"{label} {int(line.tons)} TONS")
    return out
