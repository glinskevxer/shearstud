"""Assembling one live load effect out of the four things that make it.

An influence line, a vehicle, a distribution factor and a dynamic allowance are
each easy on their own. The order they combine in is the part worth pinning
down, and it is fixed here so no report ever has to explain which order it used:

1. place the vehicle on the influence line and read the static effect;
2. add the dynamic allowance to the vehicle effect and nothing else;
3. add the lane load, which never carries the allowance;
4. multiply the whole thing by the distribution factor, which converts a lane of
   load into the share one girder carries.

Step four last matters. The distribution factor is per lane, so applying it
before the lane load is added would leave the lane load undistributed, and the
result would still be a plausible looking number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from shearstud.errors import InputError
from shearstud.loads import impact, traverse
from shearstud.loads.axles import AxleTrain
from shearstud.loads.influence import InfluenceLine
from shearstud.loads.traverse import Placement


@dataclass(frozen=True, slots=True)
class LiveLoadCase:
    """Everything about a section that does not depend on which vehicle it is."""

    label: str
    influence: InfluenceLine
    distribution_factor: float
    allowance_frac: float
    lane_load_klf: float = 0.0

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise InputError("a live load case needs a label")
        if self.distribution_factor <= 0.0:
            raise InputError(
                f"{self.label}: distribution factor {self.distribution_factor} is not positive"
            )
        if self.allowance_frac < 0.0:
            raise InputError(f"{self.label}: dynamic allowance {self.allowance_frac} is negative")
        if self.lane_load_klf < 0.0:
            raise InputError(f"{self.label}: lane load {self.lane_load_klf} is negative")


@dataclass(frozen=True, slots=True)
class LiveLoadEffect:
    """One live load answer, with every intermediate kept.

    The intermediates are kept because a rating that a district engineer cannot
    take apart is a rating they will not sign. Every number below appears on the
    printed sheet.
    """

    case: str
    vehicle: str
    static_truck: float
    truck_with_impact: float
    lane: float
    per_lane: float
    distributed: float
    placement: Placement

    @property
    def impact_share(self) -> float:
        """How much of the per lane effect came from the dynamic allowance."""
        if self.per_lane == 0.0:
            return 0.0
        return (self.truck_with_impact - self.static_truck) / self.per_lane


def evaluate(case: LiveLoadCase, train: AxleTrain, *, maximum: bool = True) -> LiveLoadEffect:
    """Work one vehicle through the four steps."""
    placement = traverse.worst_effect(case.influence, train, maximum=maximum)
    static = placement.value
    with_impact = impact.apply(static, case.allowance_frac)
    if maximum:
        lane = traverse.uniform_effect(case.influence, case.lane_load_klf)
    else:
        lane = traverse.uniform_effect_negative(case.influence, case.lane_load_klf)
    per_lane = with_impact + lane
    return LiveLoadEffect(
        case=case.label,
        vehicle=train.name,
        static_truck=static,
        truck_with_impact=with_impact,
        lane=lane,
        per_lane=per_lane,
        distributed=per_lane * case.distribution_factor,
        placement=placement,
    )


def envelope(
    case: LiveLoadCase, trains: Sequence[AxleTrain], *, maximum: bool = True
) -> LiveLoadEffect:
    """The governing vehicle for one case."""
    if not trains:
        raise InputError(f"{case.label}: an envelope needs at least one vehicle")
    results = [evaluate(case, train, maximum=maximum) for train in trains]
    key = max if maximum else min
    return key(results, key=lambda r: r.distributed)


def ratio_to(effect: LiveLoadEffect, other: LiveLoadEffect) -> float:
    """How much worse one effect is than another, for a rating comparison."""
    if other.distributed == 0.0:
        raise InputError("cannot compare against a zero effect")
    return effect.distributed / other.distributed
