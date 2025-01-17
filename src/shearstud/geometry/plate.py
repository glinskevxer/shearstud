"""Rectangular plate elements, the only primitive the section builder knows.

A built up plate girder is a web and two flanges, and a rolled shape is close
enough to three rectangles that treating it as one loses less than the mill
tolerance does. Cover plates, longitudinal stiffeners and haunch steel all fall
out of the same primitive, so the section arithmetic never grows a special case.

Every plate carries the y coordinate of its own centre measured from a datum
the caller picks. In practice that datum is the bottom of the bottom flange,
because that is where a field measurement starts from.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from shearstud.errors import GeometryError

#: Below this, a dimension is a typo or a unit mistake rather than a plate.
MIN_DIMENSION_IN: Final[float] = 1.0e-4


@dataclass(frozen=True, slots=True)
class Plate:
    """One rectangle in a cross section.

    ``width_in`` is the horizontal extent and ``height_in`` the vertical one, so
    a flange is wide and short and a web is narrow and tall. Keeping both as
    plain rectangles is what lets one formula serve every component.
    """

    label: str
    width_in: float
    height_in: float
    y_center_in: float

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise GeometryError("a plate needs a label")
        if self.width_in < MIN_DIMENSION_IN:
            raise GeometryError(f"{self.label}: width {self.width_in} is not a plate")
        if self.height_in < MIN_DIMENSION_IN:
            raise GeometryError(f"{self.label}: height {self.height_in} is not a plate")

    @property
    def area_in2(self) -> float:
        """Gross area of the rectangle."""
        return self.width_in * self.height_in

    @property
    def inertia_own_in4(self) -> float:
        """Second moment about the plate's own horizontal centroidal axis."""
        return self.width_in * self.height_in**3 / 12.0

    @property
    def y_bottom_in(self) -> float:
        """Datum coordinate of the lowest fibre."""
        return self.y_center_in - self.height_in / 2.0

    @property
    def y_top_in(self) -> float:
        """Datum coordinate of the highest fibre."""
        return self.y_center_in + self.height_in / 2.0

    def moved_to(self, y_center_in: float) -> Plate:
        """Same plate at a different height. Used when a datum shifts."""
        return Plate(self.label, self.width_in, self.height_in, y_center_in)

    def thinned_by(self, loss_in: float) -> Plate:
        """Return the plate with ``loss_in`` removed from its thinner dimension.

        Corrosion eats through the thickness, not the depth, so the smaller of
        the two dimensions is the one that loses material. A flange loses width
        only at its tips and that is a stiffness effect this model does not
        claim to capture.
        """
        if loss_in < 0.0:
            raise GeometryError(f"{self.label}: section loss cannot be negative")
        if self.width_in <= self.height_in:
            remaining_in = self.width_in - loss_in
            if remaining_in < MIN_DIMENSION_IN:
                raise GeometryError(f"{self.label}: loss {loss_in} removes the whole plate")
            return Plate(self.label, remaining_in, self.height_in, self.y_center_in)
        remaining_in = self.height_in - loss_in
        if remaining_in < MIN_DIMENSION_IN:
            raise GeometryError(f"{self.label}: loss {loss_in} removes the whole plate")
        return Plate(self.label, self.width_in, remaining_in, self.y_center_in)


def flange(label: str, width_in: float, thickness_in: float, y_center_in: float) -> Plate:
    """A horizontal plate, named the way a shop drawing names it."""
    return Plate(label, width_in=width_in, height_in=thickness_in, y_center_in=y_center_in)


def web(label: str, thickness_in: float, depth_in: float, y_center_in: float) -> Plate:
    """A vertical plate."""
    return Plate(label, width_in=thickness_in, height_in=depth_in, y_center_in=y_center_in)
