"""The structure record: everything about one bridge that a rating starts from.

This is the aggregate. It owns the span arrangement, the girder lines and the
gauge installations, and it is responsible for the invariants that cross them:
every gauge names a detail that exists, every girder is as long as the unit, and
the girder indices run from zero without a gap.

Those three checks earn their place. Each one has been violated by a real import
from the inventory spreadsheet, and each failure surfaced somewhere else: a
missing detail as a lookup error inside the fatigue evaluation, a short girder
as a station past the end during a traversal, and a gap in the indices as a
distribution factor computed for a girder that was not there.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date

from shearstud.errors import InputError
from shearstud.structure.detail import FatigueDetail
from shearstud.structure.gauge import GaugeInstall
from shearstud.structure.girder import GirderLine
from shearstud.structure.identity import StructureNumber
from shearstud.structure.span import SpanArrangement

#: Lengths closer than this are the same length.
LENGTH_TOLERANCE_FT = 0.05


@dataclass(frozen=True, slots=True)
class Structure:
    """One bridge, as the rating office holds it."""

    number: StructureNumber
    name: str
    spans: SpanArrangement
    girders: tuple[GirderLine, ...]
    gauges: tuple[GaugeInstall, ...] = ()
    year_built: int = 0
    effective_width_rule: str = "tributary"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InputError(f"{self.number}: a structure needs a name")
        if not self.girders:
            raise InputError(f"{self.number}: a structure needs at least one girder")
        self._check_girder_indices()
        self._check_girder_lengths()
        self._check_gauge_details()

    def _check_girder_indices(self) -> None:
        indices = sorted(g.layout.girder_index for g in self.girders)
        if indices != list(range(len(indices))):
            raise InputError(f"{self.number}: girder indices are {indices}, not a run from zero")

    def _check_girder_lengths(self) -> None:
        unit_ft = self.spans.total_length_ft
        for girder in self.girders:
            if abs(girder.length_ft - unit_ft) > LENGTH_TOLERANCE_FT:
                raise InputError(
                    f"{self.number}: girder {girder.girder_id} is {girder.length_ft} ft "
                    f"on a {unit_ft} ft unit"
                )

    def _check_gauge_details(self) -> None:
        known = {d.detail_id for girder in self.girders for d in girder.details}
        for install in self.gauges:
            if install.detail_id not in known:
                raise InputError(
                    f"{self.number}: gauge {install.gauge_id} watches detail "
                    f"{install.detail_id!r}, which is not on this structure"
                )

    def __iter__(self) -> Iterator[GirderLine]:
        return iter(self.girders)

    @property
    def girder_count(self) -> int:
        """How many girder lines the unit has."""
        return len(self.girders)

    @property
    def length_ft(self) -> float:
        """End to end length of the unit."""
        return self.spans.total_length_ft

    @property
    def is_instrumented(self) -> bool:
        """True when at least one gauge is on the structure."""
        return bool(self.gauges)

    def girder(self, girder_id: str) -> GirderLine:
        """One girder by id."""
        for g in self.girders:
            if g.girder_id == girder_id:
                return g
        raise InputError(f"{self.number}: no girder {girder_id!r}")

    def girder_at_index(self, index: int) -> GirderLine:
        """One girder by its position across the deck."""
        for g in self.girders:
            if g.layout.girder_index == index:
                return g
        raise InputError(f"{self.number}: no girder at index {index}")

    def exterior_girders(self) -> list[GirderLine]:
        """The girders carrying an overhang, in index order."""
        found = [g for g in self.girders if g.is_exterior]
        return sorted(found, key=lambda g: g.layout.girder_index)

    def interior_girders(self) -> list[GirderLine]:
        """The girders in a bay on both sides, in index order."""
        found = [g for g in self.girders if not g.is_exterior]
        return sorted(found, key=lambda g: g.layout.girder_index)

    def details(self) -> list[FatigueDetail]:
        """Every detail on the structure, girder order then station order."""
        out: list[FatigueDetail] = []
        for girder in self.girders:
            out.extend(girder.details)
        return out

    def detail_owner(self, detail_id: str) -> GirderLine:
        """Which girder a detail is on."""
        for girder in self.girders:
            if any(d.detail_id == detail_id for d in girder.details):
                return girder
        raise InputError(f"{self.number}: no detail {detail_id!r} on this structure")

    def live_gauges(self, when: date) -> list[GaugeInstall]:
        """Gauges installed and not yet removed on a date."""
        return sorted((g for g in self.gauges if g.is_live_on(when)), key=lambda g: g.gauge_id)

    def age_years(self, when: date) -> int:
        """How old the structure is, in whole years."""
        if self.year_built <= 0:
            raise InputError(f"{self.number}: the year built is not recorded")
        return when.year - self.year_built

    def with_girders(self, girders: Sequence[GirderLine]) -> Structure:
        """A copy carrying a different set of girder lines.

        Used to swap the drawing sections for measured ones. Everything else
        comes across, gauges included, because measuring a plate does not move
        a gauge.
        """
        return Structure(
            number=self.number,
            name=self.name,
            spans=self.spans,
            girders=tuple(girders),
            gauges=self.gauges,
            year_built=self.year_built,
            effective_width_rule=self.effective_width_rule,
        )

    def with_gauges(self, gauges: Sequence[GaugeInstall]) -> Structure:
        """A copy carrying a different set of gauge installations."""
        return Structure(
            number=self.number,
            name=self.name,
            spans=self.spans,
            girders=self.girders,
            gauges=tuple(gauges),
            year_built=self.year_built,
            effective_width_rule=self.effective_width_rule,
        )
