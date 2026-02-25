"""Influence lines as piecewise linear functions of load position.

An influence line gives one load effect at one section as a unit load walks the
structure. Everything the live load analysis does is built on that: put the
axles down, read the ordinate under each, multiply and add.

Shear influence lines jump at the section they are taken for, and the jump is
the whole point of them, so this representation allows two ordinates at the same
station. That makes the reading at a jump ambiguous, and the ambiguity is
resolved by naming it: :meth:`at` reads the limit from the right, :meth:`at_left`
reads it from the left, and :meth:`worst_at` takes whichever is larger in
magnitude, which is what a hand calculation does with a wheel sitting exactly on
the section.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

from shearstud.errors import InputError

#: Positions closer than this are the same position.
POSITION_TOLERANCE_FT = 1.0e-9


@dataclass(frozen=True, slots=True)
class InfluenceLine:
    """Ordinates against load position, joined by straight lines.

    Outside the range of ``stations_ft`` the ordinate is zero, because a load
    off the structure does not load it.
    """

    label: str
    stations_ft: tuple[float, ...]
    ordinates: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise InputError("an influence line needs a label")
        if len(self.stations_ft) != len(self.ordinates):
            raise InputError(
                f"{self.label}: {len(self.stations_ft)} stations against "
                f"{len(self.ordinates)} ordinates"
            )
        if len(self.stations_ft) < 2:
            raise InputError(f"{self.label}: an influence line needs at least two points")
        for earlier, later in zip(self.stations_ft, self.stations_ft[1:], strict=False):
            if later < earlier:
                raise InputError(f"{self.label}: stations run backwards at {later}")

    @property
    def start_ft(self) -> float:
        """First station the line covers."""
        return self.stations_ft[0]

    @property
    def end_ft(self) -> float:
        """Last station the line covers."""
        return self.stations_ft[-1]

    @property
    def length_ft(self) -> float:
        """How much structure the line covers."""
        return self.end_ft - self.start_ft

    def at(self, station_ft: float) -> float:
        """Ordinate at ``station_ft``, read from the right at a jump."""
        if station_ft < self.start_ft - POSITION_TOLERANCE_FT:
            return 0.0
        if station_ft > self.end_ft + POSITION_TOLERANCE_FT:
            return 0.0
        index = bisect_right(self.stations_ft, station_ft) - 1
        if index < 0:
            return self.ordinates[0]
        if index >= len(self.stations_ft) - 1:
            return self.ordinates[-1]
        left_ft = self.stations_ft[index]
        right_ft = self.stations_ft[index + 1]
        if right_ft - left_ft <= POSITION_TOLERANCE_FT:
            return self.ordinates[index + 1]
        fraction = (station_ft - left_ft) / (right_ft - left_ft)
        return self.ordinates[index] + fraction * (
            self.ordinates[index + 1] - self.ordinates[index]
        )

    def at_left(self, station_ft: float) -> float:
        """Ordinate at ``station_ft``, read from the left at a jump."""
        index = bisect_left(self.stations_ft, station_ft)
        on_a_point = 0 <= index < len(self.stations_ft) and (
            abs(self.stations_ft[index] - station_ft) <= POSITION_TOLERANCE_FT
        )
        if on_a_point:
            return self.ordinates[index]
        return self.at(station_ft)

    def worst_at(self, station_ft: float) -> float:
        """The larger of the two limits in magnitude, signs kept."""
        right = self.at(station_ft)
        left = self.at_left(station_ft)
        return right if abs(right) >= abs(left) else left

    def jump_at(self, station_ft: float) -> float:
        """Size of the discontinuity at a station, zero where the line is
        continuous."""
        return self.at(station_ft) - self.at_left(station_ft)

    @property
    def peak(self) -> float:
        """Largest positive ordinate."""
        return max(self.ordinates)

    @property
    def trough(self) -> float:
        """Largest negative ordinate, or the smallest positive one if the line
        never goes negative."""
        return min(self.ordinates)

    def area(self) -> float:
        """Signed area, which is what a uniform load over the whole line gives."""
        total = 0.0
        for i in range(len(self.stations_ft) - 1):
            width_ft = self.stations_ft[i + 1] - self.stations_ft[i]
            total += width_ft * (self.ordinates[i] + self.ordinates[i + 1]) / 2.0
        return total

    def positive_area(self) -> float:
        """Area of the parts above the axis, for a lane load placed to hurt."""
        return self._signed_area(positive=True)

    def negative_area(self) -> float:
        """Area of the parts below the axis, reported as a negative number."""
        return self._signed_area(positive=False)

    def _signed_area(self, *, positive: bool) -> float:
        total = 0.0
        for i in range(len(self.stations_ft) - 1):
            x0, x1 = self.stations_ft[i], self.stations_ft[i + 1]
            y0, y1 = self.ordinates[i], self.ordinates[i + 1]
            width_ft = x1 - x0
            if width_ft <= POSITION_TOLERANCE_FT:
                continue
            if (y0 >= 0.0) == (y1 >= 0.0):
                piece = width_ft * (y0 + y1) / 2.0
                if (piece > 0.0) == positive and piece != 0.0:
                    total += piece
                continue
            # The segment crosses the axis, so split it at the crossing.
            cross_ft = x0 + width_ft * abs(y0) / (abs(y0) + abs(y1))
            first = (cross_ft - x0) * y0 / 2.0
            second = (x1 - cross_ft) * y1 / 2.0
            for piece in (first, second):
                if (piece > 0.0) == positive and piece != 0.0:
                    total += piece
        return total

    def scaled(self, factor: float) -> InfluenceLine:
        """The same line with every ordinate multiplied."""
        return InfluenceLine(
            self.label, self.stations_ft, tuple(o * factor for o in self.ordinates)
        )


def line(label: str, points: Sequence[tuple[float, float]]) -> InfluenceLine:
    """Build a line from station and ordinate pairs."""
    return InfluenceLine(label, tuple(p[0] for p in points), tuple(p[1] for p in points))


def _check_section(span_ft: float, section_ft: float) -> None:
    if span_ft <= 0.0:
        raise InputError(f"span {span_ft:g} is not a span")
    if not 0.0 <= section_ft <= span_ft:
        raise InputError(f"section {section_ft:g} is not on a {span_ft:g} ft span")


def simple_moment(span_ft: float, section_ft: float) -> InfluenceLine:
    """Moment at ``section_ft`` on a simply supported span.

    The peak is a times b over L, under the section itself.
    """
    _check_section(span_ft, section_ft)
    a_ft = section_ft
    b_ft = span_ft - section_ft
    return line(
        f"M at {section_ft:g} of {span_ft:g}",
        [(0.0, 0.0), (a_ft, a_ft * b_ft / span_ft), (span_ft, 0.0)],
    )


def simple_shear(span_ft: float, section_ft: float) -> InfluenceLine:
    """Shear at ``section_ft`` on a simply supported span.

    Negative to the left of the section and positive to the right, with a unit
    jump across it. The sign convention is that positive shear is the left part
    of the beam pushing up on the right part.
    """
    _check_section(span_ft, section_ft)
    a_ft = section_ft
    b_ft = span_ft - section_ft
    return line(
        f"V at {section_ft:g} of {span_ft:g}",
        [
            (0.0, 0.0),
            (a_ft, -a_ft / span_ft),
            (a_ft, b_ft / span_ft),
            (span_ft, 0.0),
        ],
    )


def simple_reaction(span_ft: float, *, left: bool = True) -> InfluenceLine:
    """Reaction at one abutment of a simply supported span."""
    if span_ft <= 0.0:
        raise InputError(f"span {span_ft} is not a span")
    if left:
        return line(f"R left of {span_ft:g}", [(0.0, 1.0), (span_ft, 0.0)])
    return line(f"R right of {span_ft:g}", [(0.0, 0.0), (span_ft, 1.0)])
