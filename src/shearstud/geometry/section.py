"""A cross section is an ordered bag of plates and the properties that follow.

Everything downstream reads the four numbers at the bottom of this module:
area, centroid, moment of inertia and the two section moduli. The rest of the
package never touches a plate directly, which is what lets a corroded section,
a composite section and a bare rolled shape all be rated by the same code.

The datum is whatever the caller used when placing the plates. Section moduli
are reported about the section's own centroid, so the datum choice cancels out
and only the relative positions matter.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from shearstud.errors import GeometryError
from shearstud.geometry.plate import Plate


@dataclass(frozen=True, slots=True)
class Section:
    """A set of plates treated as one bending member."""

    label: str
    plates: tuple[Plate, ...]

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise GeometryError("a section needs a label")
        if not self.plates:
            raise GeometryError(f"{self.label}: a section needs at least one plate")
        seen: set[str] = set()
        for p in self.plates:
            if p.label in seen:
                raise GeometryError(f"{self.label}: duplicate plate label {p.label!r}")
            seen.add(p.label)

    def __iter__(self) -> Iterator[Plate]:
        return iter(self.plates)

    def __len__(self) -> int:
        return len(self.plates)

    def plate(self, label: str) -> Plate:
        """The plate carrying ``label``.

        Raises rather than returning ``None`` because every caller that asks for
        a plate by name is about to use its dimensions.
        """
        for p in self.plates:
            if p.label == label:
                return p
        raise GeometryError(f"{self.label}: no plate labelled {label!r}")

    @property
    def area_in2(self) -> float:
        """Gross area, ignoring holes and net section."""
        return sum(p.area_in2 for p in self.plates)

    @property
    def centroid_in(self) -> float:
        """Height of the elastic neutral axis above the datum."""
        return sum(p.area_in2 * p.y_center_in for p in self.plates) / self.area_in2

    @property
    def inertia_in4(self) -> float:
        """Second moment about the section's own horizontal centroidal axis."""
        na_in = self.centroid_in
        total = 0.0
        for p in self.plates:
            arm_in = p.y_center_in - na_in
            total += p.inertia_own_in4 + p.area_in2 * arm_in * arm_in
        return total

    @property
    def y_bottom_in(self) -> float:
        """Datum coordinate of the lowest fibre in the section."""
        return min(p.y_bottom_in for p in self.plates)

    @property
    def y_top_in(self) -> float:
        """Datum coordinate of the highest fibre in the section."""
        return max(p.y_top_in for p in self.plates)

    @property
    def depth_in(self) -> float:
        """Overall depth, extreme fibre to extreme fibre."""
        return self.y_top_in - self.y_bottom_in

    @property
    def c_bottom_in(self) -> float:
        """Distance from the neutral axis down to the bottom fibre."""
        return self.centroid_in - self.y_bottom_in

    @property
    def c_top_in(self) -> float:
        """Distance from the neutral axis up to the top fibre."""
        return self.y_top_in - self.centroid_in

    @property
    def section_modulus_bottom_in3(self) -> float:
        """Elastic section modulus referred to the bottom fibre."""
        return self.inertia_in4 / self.c_bottom_in

    @property
    def section_modulus_top_in3(self) -> float:
        """Elastic section modulus referred to the top fibre."""
        return self.inertia_in4 / self.c_top_in

    @property
    def radius_of_gyration_in(self) -> float:
        """Radius of gyration about the bending axis."""
        return math.sqrt(self.inertia_in4 / self.area_in2)

    def first_moment_above_in3(self, y_in: float) -> float:
        """Statical moment of everything above ``y_in`` about the neutral axis.

        This is the Q in the shear flow expression, and it is what sizes the
        stud spacing on a composite girder. Plates that straddle the cut are
        split, so the answer is continuous as ``y_in`` sweeps the depth.
        """
        na_in = self.centroid_in
        total = 0.0
        for p in self.plates:
            lo_in = max(p.y_bottom_in, y_in)
            hi_in = p.y_top_in
            if hi_in <= lo_in:
                continue
            piece_area_in2 = p.width_in * (hi_in - lo_in)
            piece_centre_in = (hi_in + lo_in) / 2.0
            total += piece_area_in2 * (piece_centre_in - na_in)
        return total

    def area_below_in2(self, y_in: float) -> float:
        """Area of everything below ``y_in``, plates split where they straddle.

        The plastic neutral axis search sweeps this, and so does anything that
        needs to know how the area is distributed rather than where its centroid
        is. It lives here rather than in the caller because it is the same sweep
        :meth:`first_moment_above_in3` already does, one moment lower.
        """
        total = 0.0
        for p in self.plates:
            hi_in = min(p.y_top_in, y_in)
            if hi_in > p.y_bottom_in:
                total += p.width_in * (hi_in - p.y_bottom_in)
        return total

    def width_at_in(self, y_in: float) -> float:
        """Total horizontal material at one height.

        Plates that only touch the level are counted, so this reports the width
        of the plate a level sits inside rather than zero at a boundary.
        """
        return sum(p.width_in for p in self.plates if p.y_bottom_in <= y_in <= p.y_top_in)

    def plate_edges_in(self) -> tuple[float, ...]:
        """Every distinct plate boundary height, ascending.

        The area sweep is piecewise linear between these, so a search over them
        is exact rather than a sampling.
        """
        edges = {p.y_bottom_in for p in self.plates} | {p.y_top_in for p in self.plates}
        return tuple(sorted(edges))

    def with_plates(self, plates: Iterable[Plate]) -> Section:
        """A copy of this section carrying ``plates`` instead."""
        return Section(self.label, tuple(plates))

    def rebased(self) -> Section:
        """A copy with the datum moved to the lowest fibre.

        Two sections built from different drawings compare cleanly once both
        have been rebased, and every stored section is rebased before it is
        written.
        """
        shift_in = self.y_bottom_in
        if shift_in == 0.0:
            return self
        return self.with_plates(p.moved_to(p.y_center_in - shift_in) for p in self.plates)
