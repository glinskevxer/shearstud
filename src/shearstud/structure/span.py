"""Span arrangements, and the two coordinate systems a structure is measured in.

A rating sheet gives a station along a girder from the near abutment of the span
it is in. A field inspector gives a station along the whole unit from the near
abutment of the structure. Both are called "station" on the paperwork and they
are not the same number once there is more than one span, which is the single
most common way a detail ends up located in the wrong place.

This module keeps them apart by name. ``global_station_ft`` runs from the start
of the unit; ``local_station_ft`` runs from the start of one span. Every
conversion goes through :class:`SpanArrangement`, and nothing else in the
package adds a span length to a station.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Final

from shearstud.errors import InputError

#: A span shorter than this is a slab, not a girder span, and this package has
#: nothing useful to say about it.
MIN_SPAN_FT: Final[float] = 6.0

#: Stations closer than this are the same station.
STATION_TOLERANCE_FT: Final[float] = 1.0e-3

#: How much longer a span may be than the one beside it before the unit is
#: called unbalanced. The classic three span arrangement puts the end spans
#: at four fifths of the interior one, a ratio of 1.25, so the limit has to
#: sit above that or every well proportioned unit on the books reads badly.
BALANCE_LIMIT: Final[float] = 1.35


@dataclass(frozen=True, slots=True)
class Span:
    """One span of a continuous or simple unit."""

    index: int
    length_ft: float

    def __post_init__(self) -> None:
        if self.index < 0:
            raise InputError("span index is zero based and cannot be negative")
        if self.length_ft < MIN_SPAN_FT:
            raise InputError(
                f"span {self.index} is {self.length_ft} ft, shorter than a girder span"
            )


@dataclass(frozen=True, slots=True)
class SpanArrangement:
    """The spans of one structural unit, in order, and whether they are joined.

    A three span continuous unit and three simple spans have the same lengths
    and completely different influence lines, so ``continuous`` is not a label
    on the record. It changes what every downstream analysis does.
    """

    spans: tuple[Span, ...]
    continuous: bool

    def __post_init__(self) -> None:
        if not self.spans:
            raise InputError("a unit needs at least one span")
        for position, span in enumerate(self.spans):
            if span.index != position:
                raise InputError(f"span at position {position} carries index {span.index}")
        if self.continuous and len(self.spans) == 1:
            raise InputError("a single span unit cannot be continuous")

    def __iter__(self) -> Iterator[Span]:
        return iter(self.spans)

    def __len__(self) -> int:
        return len(self.spans)

    @property
    def span_count(self) -> int:
        """How many spans the unit has."""
        return len(self.spans)

    @property
    def total_length_ft(self) -> float:
        """End to end length of the unit."""
        return sum(span.length_ft for span in self.spans)

    @property
    def lengths_ft(self) -> tuple[float, ...]:
        """Span lengths in order, the form the analysis routines want."""
        return tuple(span.length_ft for span in self.spans)

    @property
    def support_stations_ft(self) -> tuple[float, ...]:
        """Global stations of every support, both abutments included."""
        stations = [0.0]
        for span in self.spans:
            stations.append(stations[-1] + span.length_ft)
        return tuple(stations)

    @property
    def interior_support_stations_ft(self) -> tuple[float, ...]:
        """Global stations of the piers, which is where negative moment lives."""
        return self.support_stations_ft[1:-1]

    @property
    def is_balanced(self) -> bool:
        """True when no span badly outreaches the one beside it.

        Unbalanced continuous units lift at the end bearings under some load
        placements, and the rating has to be looked at by hand when they do.
        """
        return all(
            max(a, b) <= BALANCE_LIMIT * min(a, b)
            for a, b in zip(self.lengths_ft, self.lengths_ft[1:], strict=False)
        )

    def span_index_at(self, global_station_ft: float) -> int:
        """Which span a global station falls in."""
        if global_station_ft < -STATION_TOLERANCE_FT:
            raise InputError(f"station {global_station_ft} is behind the start of the unit")
        total_ft = self.total_length_ft
        if global_station_ft > total_ft + STATION_TOLERANCE_FT:
            raise InputError(
                f"station {global_station_ft} is past the end of the unit at {total_ft}"
            )
        starts = list(self.support_stations_ft[:-1])
        return min(max(0, bisect_right(starts, global_station_ft) - 1), self.span_count - 1)

    def to_local(self, global_station_ft: float) -> tuple[int, float]:
        """Global station to the span it is in and the station within it."""
        index = self.span_index_at(global_station_ft)
        return index, global_station_ft - self.support_stations_ft[index]

    def to_global(self, span_index: int, local_station_ft: float) -> float:
        """Station within a span back to a station along the unit."""
        if not 0 <= span_index < self.span_count:
            raise InputError(f"no span {span_index} in a {self.span_count} span unit")
        span = self.spans[span_index]
        if local_station_ft < -STATION_TOLERANCE_FT:
            raise InputError(f"local station {local_station_ft} is behind the span")
        if local_station_ft > span.length_ft + STATION_TOLERANCE_FT:
            raise InputError(
                f"local station {local_station_ft} is past span {span_index} at {span.length_ft}"
            )
        return self.support_stations_ft[span_index] + local_station_ft


def simple(length_ft: float) -> SpanArrangement:
    """A single simply supported span, which most of the inventory is."""
    return SpanArrangement((Span(0, length_ft),), continuous=False)


def series(lengths_ft: Sequence[float], *, continuous: bool) -> SpanArrangement:
    """Build an arrangement from a list of span lengths."""
    spans = tuple(Span(i, length_ft) for i, length_ft in enumerate(lengths_ft))
    return SpanArrangement(spans, continuous=continuous)
