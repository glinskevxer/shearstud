"""Building the office's worklist out of the book, and saying what is missing.

The ranking wants a rating factor, a fatigue life and an inspection row for
every structure. Real inventories do not have all three for every structure and
never will: something was imported last week and has not been rated, something
was rated in 1998 and never instrumented, something has a gauge on it and no
inspection since the programme started.

The wrong thing to do with those is to fill in a default and rank them anyway. A
structure ranked on a guessed condition rating sits in the middle of the list
where nobody looks at it again, and the guess is never revisited because the
list looks complete. So a structure missing anything is left off the ranking and
put on a second list that says what it is missing. The second list is the one
worth reading first.

The one thing that is defaulted is the fatigue life, and only upwards. A
structure nobody has measured is not thereby a structure with a fatigue problem,
and putting every unmeasured structure in the retrofit band would bury the ones
that are actually cracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from shearstud.errors import StorageError
from shearstud.program import priority
from shearstud.program.priority import Candidate
from shearstud.store import assessment as asm
from shearstud.store import inventory
from shearstud.store import programme as prog

#: Why a structure could not be ranked.
GAP_NO_PROGRAMME = "never inspected under this programme"
GAP_NEVER_RATED = "no load rating on record"
GAP_REASONS: Final[tuple[str, ...]] = (GAP_NO_PROGRAMME, GAP_NEVER_RATED)

#: What an unmeasured structure's fatigue life is taken to be. Above every
#: threshold in the banding, so the absence of a measurement never puts a
#: structure into the retrofit band on its own.
UNMEASURED_LIFE_YEARS: Final[float] = 100.0


@dataclass(frozen=True, slots=True)
class Gap:
    """A structure that could not be ranked, and what it is short of."""

    structure_number: str
    reason: str

    def __post_init__(self) -> None:
        if self.reason not in GAP_REASONS:
            raise StorageError(f"unknown gap reason {self.reason!r}")


@dataclass(frozen=True, slots=True)
class Worklist:
    """The ranked inventory, and everything that could not be ranked."""

    ranked: tuple[Candidate, ...]
    gaps: tuple[Gap, ...]
    unmeasured: tuple[str, ...]

    @property
    def structure_count(self) -> int:
        """Every structure the run looked at."""
        return len(self.ranked) + len(self.gaps)

    @property
    def ranked_frac(self) -> float:
        """Share of the inventory the ranking actually covers."""
        if self.structure_count == 0:
            return 0.0
        return len(self.ranked) / self.structure_count

    def gaps_for(self, reason: str) -> list[str]:
        """Structure numbers short of one thing, sorted."""
        if reason not in GAP_REASONS:
            raise StorageError(f"unknown gap reason {reason!r}")
        return sorted(g.structure_number for g in self.gaps if g.reason == reason)

    def counts(self) -> dict[str, int]:
        """How many ranked structures fell in each band."""
        return priority.counts(list(self.ranked))

    def top(self, limit: int) -> list[Candidate]:
        """The front of the ranked list."""
        return priority.top(list(self.ranked), limit)


def credited_life_years(path: Path | str, number: str) -> tuple[float, bool]:
    """The life to rank a structure on, and whether anyone measured it.

    Two answers rather than one because they are used for different things.
    The number goes into the banding; the flag goes onto the report, so that a
    structure sitting comfortably on a default can be told from one sitting
    comfortably on a reading.
    """
    measured = asm.structure_life_years(path, number)
    if measured is None:
        return UNMEASURED_LIFE_YEARS, False
    return min(measured, UNMEASURED_LIFE_YEARS), True


def _candidate_for(path: Path | str, number: str) -> Candidate | Gap:
    row = prog.find(path, number)
    if row is None:
        return Gap(number, GAP_NO_PROGRAMME)
    try:
        governing = asm.governing_rating(path, number)
    except StorageError:
        return Gap(number, GAP_NEVER_RATED)
    life_years, _ = credited_life_years(path, number)
    policy = inventory.load_policy(path, number)
    return row.candidate(
        rating_factor=governing.rating_factor,
        fatigue_life_years=life_years,
        nonredundant=policy.is_nonredundant,
    )


def build(path: Path | str) -> Worklist:
    """Rank everything that can be ranked and name everything that cannot."""
    ranked: list[Candidate] = []
    gaps: list[Gap] = []
    unmeasured: list[str] = []
    for number in inventory.numbers(path):
        found = _candidate_for(path, number)
        if isinstance(found, Gap):
            gaps.append(found)
            continue
        ranked.append(found)
        if not credited_life_years(path, number)[1]:
            unmeasured.append(number)
    return Worklist(
        ranked=tuple(priority.worklist(ranked)),
        gaps=tuple(gaps),
        unmeasured=tuple(unmeasured),
    )
