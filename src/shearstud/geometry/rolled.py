"""The rolled shape catalogue, and the three plate idealisation of a W shape.

Older stringer spans are rolled beams rather than welded girders, so the
catalogue has to exist. It carries the published area and inertia alongside the
plate dimensions, and the two disagree by about one and a half percent because
the mill fillets are real steel that three rectangles cannot represent.

That disagreement is not smoothed over. ``RolledShape.section()`` returns the
idealisation, ``RolledShape.inertia_in4`` returns the published number, and
callers pick. Fatigue work wants the idealisation because it needs a fibre
distance to go with the inertia; a quick capacity check wants the published one.
"""

from __future__ import annotations

import csv
import functools
from dataclasses import dataclass
from pathlib import Path

from shearstud.errors import ConfigError
from shearstud.geometry.plate import flange, web
from shearstud.geometry.section import Section

CATALOGUE_PATH = Path(__file__).resolve().parent.parent / "data" / "rolled_shapes.csv"

#: How far the three plate idealisation is allowed to sit from the published
#: properties before the catalogue row is treated as a typo. Fillet steel costs
#: between one and a half and three and a quarter percent across the catalogue,
#: the worst of it on the narrow flanged deep shapes, so four percent leaves
#: headroom without letting a transposed digit through.
IDEALISATION_TOLERANCE_FRAC = 0.04


@dataclass(frozen=True, slots=True)
class RolledShape:
    """One row of the catalogue."""

    designation: str
    depth_in: float
    flange_width_in: float
    flange_thickness_in: float
    web_thickness_in: float
    area_in2: float
    inertia_in4: float
    modulus_in3: float

    @property
    def web_depth_in(self) -> float:
        """Clear depth between the flanges, ignoring the fillets."""
        return self.depth_in - 2.0 * self.flange_thickness_in

    def section(self) -> Section:
        """The three plate idealisation, based at the bottom of the shape."""
        tf_in = self.flange_thickness_in
        return Section(
            self.designation,
            (
                flange(
                    "bottom",
                    width_in=self.flange_width_in,
                    thickness_in=tf_in,
                    y_center_in=tf_in / 2.0,
                ),
                web(
                    "web",
                    thickness_in=self.web_thickness_in,
                    depth_in=self.web_depth_in,
                    y_center_in=self.depth_in / 2.0,
                ),
                flange(
                    "top",
                    width_in=self.flange_width_in,
                    thickness_in=tf_in,
                    y_center_in=self.depth_in - tf_in / 2.0,
                ),
            ),
        )

    def idealisation_error_frac(self) -> float:
        """How far the idealised inertia falls below the published one."""
        return abs(self.section().inertia_in4 - self.inertia_in4) / self.inertia_in4


def _row_to_shape(row: dict[str, str], line: int) -> RolledShape:
    try:
        return RolledShape(
            designation=row["designation"].strip(),
            depth_in=float(row["depth_in"]),
            flange_width_in=float(row["flange_width_in"]),
            flange_thickness_in=float(row["flange_thickness_in"]),
            web_thickness_in=float(row["web_thickness_in"]),
            area_in2=float(row["area_in2"]),
            inertia_in4=float(row["inertia_in4"]),
            modulus_in3=float(row["modulus_in3"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"{CATALOGUE_PATH.name} line {line}: {exc}") from exc


@functools.lru_cache(maxsize=1)
def catalogue() -> dict[str, RolledShape]:
    """Every shape in the catalogue, keyed by designation.

    Cached because it is read once per process and never changes. The cache is
    on the module function rather than a module level constant so that import
    time stays free of file access.
    """
    if not CATALOGUE_PATH.exists():
        raise ConfigError(f"rolled shape catalogue missing at {CATALOGUE_PATH}")
    shapes: dict[str, RolledShape] = {}
    with CATALOGUE_PATH.open(newline="", encoding="utf-8") as fh:
        for line, row in enumerate(csv.DictReader(fh), start=2):
            shape = _row_to_shape(row, line)
            if shape.designation in shapes:
                raise ConfigError(f"duplicate designation {shape.designation!r} on line {line}")
            shapes[shape.designation] = shape
    if not shapes:
        raise ConfigError("rolled shape catalogue is empty")
    return shapes


def shape(designation: str) -> RolledShape:
    """Look one shape up by its designation, case and space insensitive."""
    key = designation.strip().upper().replace(" ", "")
    shapes = catalogue()
    if key not in shapes:
        raise ConfigError(f"unknown rolled shape {designation!r}")
    return shapes[key]


def designations() -> list[str]:
    """Catalogue keys in file order, which is deepest first."""
    return list(catalogue())
