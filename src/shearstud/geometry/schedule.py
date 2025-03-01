"""The section schedule: which cross section is in force at which station.

A girder is not one section. Flanges get thicker over the piers, cover plates
start and stop, and on the older stringers the cover plate ends are the worst
fatigue detail on the structure. Everything downstream that needs a section
needs it *at a station*, so the schedule is the object that gets passed around
rather than a bare section.

The schedule is closed and contiguous by construction. There is no gap and no
overlap, and a station outside the girder is an error rather than a clamp,
because a station outside the girder means somebody's coordinates are wrong and
clamping would hide that until the answer came out strange.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from shearstud.errors import GeometryError
from shearstud.geometry.section import Section

#: Stations closer together than this are the same station. A cover plate end
#: is located to the nearest inch on a drawing, so a thousandth of a foot is
#: well inside the noise.
STATION_TOLERANCE_FT = 1.0e-3


@dataclass(frozen=True, slots=True)
class SectionRun:
    """One stretch of girder that carries a single cross section."""

    from_station_ft: float
    to_station_ft: float
    section: Section

    def __post_init__(self) -> None:
        if self.from_station_ft < 0.0:
            raise GeometryError(f"run starts at {self.from_station_ft}, behind the datum")
        if self.to_station_ft <= self.from_station_ft + STATION_TOLERANCE_FT:
            raise GeometryError(
                f"run from {self.from_station_ft} to {self.to_station_ft} has no length"
            )

    @property
    def length_ft(self) -> float:
        """How much girder this run covers."""
        return self.to_station_ft - self.from_station_ft

    def contains(self, station_ft: float) -> bool:
        """Half open on the far end, so adjacent runs do not both claim a
        transition station."""
        return self.from_station_ft - STATION_TOLERANCE_FT <= station_ft < self.to_station_ft


@dataclass(frozen=True, slots=True)
class GirderSchedule:
    """Every run on one girder, in order, with no gaps."""

    label: str
    runs: tuple[SectionRun, ...]

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise GeometryError("a schedule needs a label")
        if not self.runs:
            raise GeometryError(f"{self.label}: a schedule needs at least one run")
        if self.runs[0].from_station_ft > STATION_TOLERANCE_FT:
            raise GeometryError(
                f"{self.label}: the first run starts at {self.runs[0].from_station_ft}, not zero"
            )
        for earlier, later in zip(self.runs, self.runs[1:], strict=False):
            gap_ft = later.from_station_ft - earlier.to_station_ft
            if abs(gap_ft) > STATION_TOLERANCE_FT:
                word = "gap" if gap_ft > 0.0 else "overlap"
                raise GeometryError(
                    f"{self.label}: {word} of {abs(gap_ft):.3f} ft at station "
                    f"{earlier.to_station_ft:.3f}"
                )

    def __iter__(self) -> Iterator[SectionRun]:
        return iter(self.runs)

    def __len__(self) -> int:
        return len(self.runs)

    @property
    def length_ft(self) -> float:
        """Girder length the schedule covers."""
        return self.runs[-1].to_station_ft

    @property
    def is_uniform(self) -> bool:
        """True when the whole girder is one section, which most short spans
        are and which lets several callers skip a lookup per station."""
        return len(self.runs) == 1

    @property
    def transitions_ft(self) -> tuple[float, ...]:
        """Stations where the section changes, interior ones only."""
        return tuple(run.to_station_ft for run in self.runs[:-1])

    def run_at(self, station_ft: float) -> SectionRun:
        """The run in force at ``station_ft``."""
        if station_ft < -STATION_TOLERANCE_FT:
            raise GeometryError(f"{self.label}: station {station_ft} is behind the datum")
        if station_ft > self.length_ft + STATION_TOLERANCE_FT:
            raise GeometryError(
                f"{self.label}: station {station_ft} is past the end at {self.length_ft}"
            )
        starts = [run.from_station_ft for run in self.runs]
        index = max(0, bisect_right(starts, station_ft) - 1)
        return self.runs[index]

    def section_at(self, station_ft: float) -> Section:
        """The cross section in force at ``station_ft``."""
        return self.run_at(station_ft).section

    def sections(self) -> tuple[Section, ...]:
        """Every distinct section in the schedule, in station order."""
        return tuple(run.section for run in self.runs)


def uniform(label: str, section: Section, length_ft: float) -> GirderSchedule:
    """A schedule for a girder that never changes section."""
    return GirderSchedule(label, (SectionRun(0.0, length_ft, section),))


def from_breaks(
    label: str, sections: Sequence[Section], breaks_ft: Iterable[float], length_ft: float
) -> GirderSchedule:
    """Build a schedule from n sections and the n minus 1 stations between them.

    This is the shape a drawing gives it in: a list of plate girder sections and
    the stations where one stops and the next starts.
    """
    edges = [0.0, *sorted(breaks_ft), length_ft]
    if len(edges) != len(sections) + 1:
        raise GeometryError(
            f"{label}: {len(sections)} sections need {len(sections) - 1} breaks, "
            f"got {len(edges) - 2}"
        )
    runs = tuple(SectionRun(edges[i], edges[i + 1], section) for i, section in enumerate(sections))
    return GirderSchedule(label, runs)
