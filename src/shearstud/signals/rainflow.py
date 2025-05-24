"""Rainflow cycle counting, four point method.

Fatigue damage is done by closed hysteresis loops, not by peaks, and a strain
record from a bridge is full of small loops nested inside big ones. Rainflow
counting is what turns the record into the list of loops that actually closed.
It is the one piece of this package where a plausible looking wrong answer is
easiest to produce, so the method is written out rather than reached for from a
library.

The four point rule: take the last four turning points, call their three ranges
r1, r2 and r3. If the middle range is no bigger than either of its neighbours,
the two middle points form a closed cycle. Extract it, drop those two points,
and look again. What is left when no more cycles close is the residue.

Two decisions the caller has to make and this module will not make silently:

* **the residue**. Repeating it and counting again closes every loop and is what
  a life calculation wants. Counting it as half cycles is what a comparison
  against a reference count wants. ``close_residue`` picks;
* **the gate**. Reversals smaller than the gate are electrical noise on a quiet
  bridge and real cycles on a busy one, and the gate belongs to the channel, not
  to this function. It defaults to zero, which counts everything.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from shearstud.errors import RecordError
from shearstud.signals.series import StrainRecord

#: How many gate filtering passes to run before giving up. Each pass removes at
#: least one point, so this can only bite on an absurd input.
MAX_GATE_PASSES = 1000


@dataclass(frozen=True, slots=True)
class Cycle:
    """One closed loop, or half of one."""

    range_ue: float
    mean_ue: float
    count: float

    def __post_init__(self) -> None:
        if self.range_ue < 0.0:
            raise RecordError(f"cycle range {self.range_ue} is negative")
        if self.count <= 0.0:
            raise RecordError(f"cycle count {self.count} is not a count")

    @property
    def peak_ue(self) -> float:
        """Upper turning point of the loop."""
        return self.mean_ue + self.range_ue / 2.0

    @property
    def trough_ue(self) -> float:
        """Lower turning point of the loop."""
        return self.mean_ue - self.range_ue / 2.0

    @property
    def is_half(self) -> bool:
        """True for a residue cycle counted as a half."""
        return self.count == 0.5


def _reversals(values: Sequence[float]) -> list[float]:
    """Keep only the points where the signal changes direction."""
    distinct: list[float] = []
    for value in values:
        if not distinct or value != distinct[-1]:
            distinct.append(value)
    if len(distinct) < 3:
        return distinct
    out = [distinct[0]]
    for index in range(1, len(distinct) - 1):
        rising = distinct[index] - distinct[index - 1]
        falling = distinct[index + 1] - distinct[index]
        if rising * falling < 0.0:
            out.append(distinct[index])
    out.append(distinct[-1])
    return out


def turning_points(values: Sequence[float], gate_ue: float = 0.0) -> list[float]:
    """Reversals in a series, with reversals smaller than the gate removed.

    Removing a small reversal can leave two points going the same way, so the
    filter and the reversal extraction are run alternately until nothing more
    changes. Doing one pass of each leaves a sequence that is not alternating,
    and the four point rule quietly gives wrong answers on it.
    """
    if gate_ue < 0.0:
        raise RecordError(f"gate {gate_ue} is negative")
    points = _reversals(values)
    if gate_ue == 0.0:
        return points
    for _ in range(MAX_GATE_PASSES):
        kept = [points[0]]
        for value in points[1:]:
            if abs(value - kept[-1]) >= gate_ue:
                kept.append(value)
        rebuilt = _reversals(kept)
        if rebuilt == points:
            return points
        points = rebuilt
    return points


def _extract(points: list[float]) -> tuple[list[Cycle], list[float]]:
    """Run the four point rule over a list of turning points."""
    residue: list[float] = []
    cycles: list[Cycle] = []
    for point in points:
        residue.append(point)
        while len(residue) >= 4:
            first, second, third, fourth = residue[-4:]
            middle = abs(third - second)
            if middle <= abs(second - first) and middle <= abs(fourth - third):
                cycles.append(Cycle(range_ue=middle, mean_ue=(second + third) / 2.0, count=1.0))
                del residue[-3:-1]
            else:
                break
    return cycles, residue


def count_cycles(
    values: Sequence[float], gate_ue: float = 0.0, *, close_residue: bool = True
) -> list[Cycle]:
    """Every closed loop in a series, largest range last.

    Order is the order the loops closed in, which is the order a damage
    calculation wants when it is asked to report where in the record the damage
    came from.
    """
    points = turning_points(values, gate_ue)
    if len(points) < 3:
        return []
    cycles, residue = _extract(points)
    if not close_residue:
        cycles.extend(
            Cycle(range_ue=abs(b - a), mean_ue=(a + b) / 2.0, count=0.5)
            for a, b in pairwise(residue)
        )
        return cycles
    closed, _ = _extract(_reversals([*residue, *residue]))
    cycles.extend(closed)
    return cycles


def count_record(
    record: StrainRecord, gate_ue: float = 0.0, *, close_residue: bool = True
) -> list[Cycle]:
    """Cycle count one strain record."""
    return count_cycles(record.samples_ue, gate_ue, close_residue=close_residue)


def total_count(cycles: Sequence[Cycle]) -> float:
    """How many cycles a list represents, halves counted as halves."""
    return sum(cycle.count for cycle in cycles)


def largest_range_ue(cycles: Sequence[Cycle]) -> float:
    """The biggest loop in the list, or zero when there are none."""
    if not cycles:
        return 0.0
    return max(cycle.range_ue for cycle in cycles)


def equivalent_range_ue(cycles: Sequence[Cycle], exponent: float = 3.0) -> float:
    """The single range that would do the same damage as the whole list.

    This is the root mean cube for the usual exponent of three, which is what
    the fatigue provisions are written around. It is the number a report quotes
    when it has to give one range for a day of traffic.
    """
    if exponent <= 0.0:
        raise RecordError(f"exponent {exponent} is not positive")
    total = total_count(cycles)
    if total <= 0.0:
        return 0.0
    weighted = sum(cycle.count * math.pow(cycle.range_ue, exponent) for cycle in cycles)
    return math.pow(weighted / total, 1.0 / exponent)
