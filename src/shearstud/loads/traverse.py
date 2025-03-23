"""Driving a vehicle across an influence line and finding where it hurts most.

The search is exact rather than a scan, and the reason is worth stating because
it is what makes the answer defensible. The load effect of an axle train on a
piecewise linear influence line is itself piecewise linear in the position of
the train, and its breakpoints are exactly the positions where some axle sits on
some vertex of the line. A piecewise linear function takes its extremes at its
breakpoints, so enumerating axle over vertex positions finds the true maximum.
A fixed step scan does not, and on a shear line with a jump in it a scan can
miss the governing position entirely.

Both travel directions are tried, because an unsymmetric truck on an unsymmetric
influence line gives different answers each way and the rating takes the worse.
"""

from __future__ import annotations

from dataclasses import dataclass

from shearstud.errors import InputError
from shearstud.loads.axles import AxleTrain
from shearstud.loads.influence import InfluenceLine

#: Positions closer than this are the same position.
POSITION_TOLERANCE_FT = 1.0e-9


@dataclass(frozen=True, slots=True)
class Placement:
    """Where a vehicle was when it produced a load effect."""

    value: float
    lead_position_ft: float
    reversed_travel: bool
    vehicle: str

    @property
    def direction(self) -> str:
        """How a report writes the travel direction."""
        return "back" if self.reversed_travel else "ahead"


def effect(il: InfluenceLine, train: AxleTrain, lead_position_ft: float) -> float:
    """Load effect with the lead axle at ``lead_position_ft``.

    Axles behind the lead axle sit at decreasing station, which is what makes
    the vehicle face forwards. Axles that have fallen off either end of the line
    read zero and cost nothing.
    """
    total = 0.0
    for offset_ft, weight_kip in zip(train.offsets_ft, train.weights_kip, strict=True):
        total += weight_kip * il.at(lead_position_ft - offset_ft)
    return total


def worst_effect(
    il: InfluenceLine, train: AxleTrain, *, maximum: bool = True, both_ways: bool = True
) -> Placement:
    """The governing placement of one vehicle on one influence line.

    ``maximum`` picks the largest positive effect; set it false to find the most
    negative one, which is what a negative moment region is rated for.
    """
    candidates = [(train, False)]
    if both_ways:
        candidates.append((train.reversed_train(), True))

    best: Placement | None = None
    for candidate, is_reversed in candidates:
        for lead_position_ft in _candidate_positions(il, candidate):
            value = effect(il, candidate, lead_position_ft)
            if best is None or _is_better(value, best.value, maximum=maximum):
                best = Placement(
                    value=value,
                    lead_position_ft=lead_position_ft,
                    reversed_travel=is_reversed,
                    vehicle=train.name,
                )
    if best is None:
        raise InputError(f"{train.name}: no placement was possible on {il.label}")
    return best


def _is_better(candidate: float, incumbent: float, *, maximum: bool) -> bool:
    return candidate > incumbent if maximum else candidate < incumbent


def _candidate_positions(il: InfluenceLine, train: AxleTrain) -> list[float]:
    """Every lead axle position that puts some axle on some vertex.

    Positions that would leave every axle off the line are dropped, so a short
    line and a long vehicle do not produce a pile of zero valued placements.
    """
    positions: set[float] = set()
    for vertex_ft in il.stations_ft:
        for offset_ft in train.offsets_ft:
            positions.add(vertex_ft + offset_ft)
    keep = [
        p
        for p in positions
        if p >= il.start_ft - POSITION_TOLERANCE_FT
        and p - train.length_ft <= il.end_ft + POSITION_TOLERANCE_FT
    ]
    return sorted(keep)


def envelope(il: InfluenceLine, trains: list[AxleTrain], *, maximum: bool = True) -> Placement:
    """The governing placement across a fleet of vehicles."""
    if not trains:
        raise InputError("an envelope needs at least one vehicle")
    best: Placement | None = None
    for train in trains:
        placement = worst_effect(il, train, maximum=maximum)
        if best is None or _is_better(placement.value, best.value, maximum=maximum):
            best = placement
    assert best is not None
    return best


def uniform_effect(il: InfluenceLine, load_klf: float, *, adverse_only: bool = True) -> float:
    """Load effect of a uniform lane load laid along the influence line.

    ``adverse_only`` places the load only where it hurts, which is what the
    specification asks for on a continuous unit and what makes a lane load on a
    two span structure worse than laying it everywhere.
    """
    if load_klf < 0.0:
        raise InputError(f"lane load {load_klf} is negative")
    if not adverse_only:
        return load_klf * il.area()
    return load_klf * il.positive_area()


def uniform_effect_negative(il: InfluenceLine, load_klf: float) -> float:
    """Uniform load placed only where it drives the effect negative."""
    if load_klf < 0.0:
        raise InputError(f"lane load {load_klf} is negative")
    return load_klf * il.negative_area()
