"""Effective flange width, under both editions this inventory is rated with.

Two rules live here, and the reason is that the file cabinet has structures
rated either way. The pre 2008 rule takes the least of three limits and the
current one takes the tributary width outright. The current rule is not always
the generous one: on a long span with a wide overhang the old span over four
limit can beat it, so neither can be substituted for the other.

Which rule applies is a property of the structure record, not of this module.
``width_for`` takes the rule by name and refuses an unknown one rather than
falling back, because a silent fallback here changes a rating by a few percent
in a direction nobody chose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from shearstud.errors import GeometryError
from shearstud.geometry.section import Section
from shearstud.units import ft_to_in

#: The two rule names the structure record may carry.
RULE_TRIBUTARY: Final[str] = "tributary"
RULE_LEGACY: Final[str] = "legacy"
RULES: Final[tuple[str, ...]] = (RULE_TRIBUTARY, RULE_LEGACY)

#: Slab multiplier in the legacy interior limit, AASHTO LRFD 4.6.2.6.1 as it
#: read before the 2008 interim.
LEGACY_SLAB_MULTIPLE: Final[float] = 12.0

#: Slab multiplier in the legacy overhang limit, half the interior one.
LEGACY_OVERHANG_SLAB_MULTIPLE: Final[float] = 6.0


@dataclass(frozen=True, slots=True)
class DeckLayout:
    """Where one girder sits in the cross section.

    ``spacing_left_ft`` and ``spacing_right_ft`` are the centre to centre
    distances to the neighbouring girders. An exterior girder has an overhang
    on one side instead of a neighbour, and carries ``overhang_ft`` for it.
    """

    girder_index: int
    spacing_left_ft: float
    spacing_right_ft: float
    overhang_ft: float
    slab_thickness_in: float

    def __post_init__(self) -> None:
        if self.girder_index < 0:
            raise GeometryError("girder index is zero based and cannot be negative")
        if self.slab_thickness_in <= 0.0:
            raise GeometryError("slab thickness must be positive")
        if self.overhang_ft < 0.0:
            raise GeometryError("overhang cannot be negative")
        if self.spacing_left_ft < 0.0 or self.spacing_right_ft < 0.0:
            raise GeometryError("girder spacing cannot be negative")
        if self.spacing_left_ft == 0.0 and self.spacing_right_ft == 0.0:
            raise GeometryError("a girder needs a neighbour on at least one side")
        if self.is_exterior and self.overhang_ft == 0.0:
            raise GeometryError("an exterior girder needs an overhang")
        if not self.is_exterior and self.overhang_ft > 0.0:
            raise GeometryError("an interior girder has no overhang to carry")

    @property
    def is_exterior(self) -> bool:
        """True when one side of this girder is an overhang rather than a bay."""
        return self.spacing_left_ft == 0.0 or self.spacing_right_ft == 0.0

    @property
    def interior_half_width_ft(self) -> float:
        """Half the bay on each side that has one."""
        return (self.spacing_left_ft + self.spacing_right_ft) / 2.0

    @property
    def average_spacing_ft(self) -> float:
        """Mean of the bays this girder touches, ignoring the overhang side."""
        bays = [s for s in (self.spacing_left_ft, self.spacing_right_ft) if s > 0.0]
        return sum(bays) / len(bays)


def tributary_width_in(layout: DeckLayout) -> float:
    """Half the bay each side, plus the whole overhang on an exterior girder."""
    width_ft = layout.interior_half_width_ft + layout.overhang_ft
    return ft_to_in(width_ft)


def legacy_interior_width_in(layout: DeckLayout, section: Section, span_ft: float) -> float:
    """The least of the three pre 2008 interior limits."""
    top = section.plate("top")
    web_thickness_in = section.plate("web").width_in
    quarter_span_in = ft_to_in(span_ft) / 4.0
    slab_limit_in = LEGACY_SLAB_MULTIPLE * layout.slab_thickness_in + max(
        web_thickness_in, top.width_in / 2.0
    )
    spacing_in = ft_to_in(layout.average_spacing_ft)
    return min(quarter_span_in, slab_limit_in, spacing_in)


def legacy_exterior_width_in(layout: DeckLayout, section: Section, span_ft: float) -> float:
    """Half the interior width plus the least of the three overhang limits."""
    top = section.plate("top")
    web_thickness_in = section.plate("web").width_in
    eighth_span_in = ft_to_in(span_ft) / 8.0
    slab_limit_in = LEGACY_OVERHANG_SLAB_MULTIPLE * layout.slab_thickness_in + max(
        web_thickness_in / 2.0, top.width_in / 4.0
    )
    overhang_in = ft_to_in(layout.overhang_ft)
    half_interior_in = legacy_interior_width_in(layout, section, span_ft) / 2.0
    return half_interior_in + min(eighth_span_in, slab_limit_in, overhang_in)


def width_for(rule: str, layout: DeckLayout, section: Section, span_ft: float) -> float:
    """Effective flange width under the named rule."""
    if span_ft <= 0.0:
        raise GeometryError(f"span {span_ft} is not a span")
    if rule == RULE_TRIBUTARY:
        return tributary_width_in(layout)
    if rule == RULE_LEGACY:
        if layout.is_exterior:
            return legacy_exterior_width_in(layout, section, span_ft)
        return legacy_interior_width_in(layout, section, span_ft)
    raise GeometryError(f"unknown effective width rule {rule!r}, expected one of {RULES}")
