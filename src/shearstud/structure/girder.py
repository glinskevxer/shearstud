"""A girder line: the section schedule, where it sits in the deck, and what is
welded to it.

This is the object every analysis is handed. It knows enough to answer "what
section is at this station", "how much of a lane does this girder carry" and
"what details are near here", and it knows nothing about loads, cycles or
ratings. Keeping it that way is what lets the same girder be rated for strength
and evaluated for fatigue without either analysis reaching into the other.

The details are held sorted by station and the class enforces that every one of
them lands on the girder, because a detail at station 300 on a 120 foot girder
is a data entry error that otherwise surfaces two layers away as a section
lookup failure.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from shearstud.errors import InputError
from shearstud.geometry.composite import CompositeGirder, DeckSlab
from shearstud.geometry.effective import DeckLayout
from shearstud.geometry.schedule import GirderSchedule
from shearstud.geometry.section import Section
from shearstud.structure.detail import FatigueDetail

#: Stations closer together than this are the same station.
STATION_TOLERANCE_FT = 1.0e-3


@dataclass(frozen=True, slots=True)
class GirderLine:
    """One girder through one unit."""

    girder_id: str
    schedule: GirderSchedule
    layout: DeckLayout
    deck: DeckSlab
    details: tuple[FatigueDetail, ...] = ()

    def __post_init__(self) -> None:
        if not self.girder_id.strip():
            raise InputError("a girder needs an id")
        length_ft = self.schedule.length_ft
        for d in self.details:
            if d.station_ft > length_ft + STATION_TOLERANCE_FT:
                raise InputError(
                    f"{self.girder_id}: detail {d.detail_id} is at station "
                    f"{d.station_ft}, past the end at {length_ft}"
                )
        ids = [d.detail_id for d in self.details]
        if len(set(ids)) != len(ids):
            raise InputError(f"{self.girder_id}: two details share an id")
        stations = [d.station_ft for d in self.details]
        if stations != sorted(stations):
            raise InputError(f"{self.girder_id}: details are not in station order")

    def __iter__(self) -> Iterator[FatigueDetail]:
        return iter(self.details)

    @property
    def length_ft(self) -> float:
        """How long the girder is."""
        return self.schedule.length_ft

    @property
    def is_exterior(self) -> bool:
        """True when this girder carries the overhang."""
        return self.layout.is_exterior

    def section_at(self, station_ft: float) -> Section:
        """Bare steel section in force at a station."""
        return self.schedule.section_at(station_ft)

    def composite_at(self, station_ft: float) -> CompositeGirder:
        """The three stage composite girder at a station."""
        return CompositeGirder(steel=self.section_at(station_ft), deck=self.deck)

    def detail(self, detail_id: str) -> FatigueDetail:
        """One detail by id."""
        for d in self.details:
            if d.detail_id == detail_id:
                return d
        raise InputError(f"{self.girder_id}: no detail {detail_id!r}")

    def details_near(self, station_ft: float, window_ft: float) -> list[FatigueDetail]:
        """Every detail within ``window_ft`` of a station."""
        if window_ft < 0.0:
            raise InputError(f"{self.girder_id}: window {window_ft} is negative")
        return [d for d in self.details if abs(d.station_ft - station_ft) <= window_ft]

    def instrumented_details(self) -> list[FatigueDetail]:
        """Details a gauge is watching, in station order."""
        return [d for d in self.details if d.is_instrumented]

    def gauge_ids(self) -> list[str]:
        """Every gauge on this girder, sorted and without repeats."""
        found: set[str] = set()
        for d in self.details:
            found.update(d.gauge_ids)
        return sorted(found)

    def with_details(self, details: Sequence[FatigueDetail]) -> GirderLine:
        """A copy carrying a different set of details, re sorted."""
        ordered = tuple(sorted(details, key=lambda d: (d.station_ft, d.detail_id)))
        return GirderLine(
            girder_id=self.girder_id,
            schedule=self.schedule,
            layout=self.layout,
            deck=self.deck,
            details=ordered,
        )

    def add_detail(self, new_detail: FatigueDetail) -> GirderLine:
        """A copy with one more detail on it."""
        return self.with_details([*self.details, new_detail])
