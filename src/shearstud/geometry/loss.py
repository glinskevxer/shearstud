"""Section loss, from ultrasonic thickness readings to a reduced section.

Corrosion is what turns a rating from an office exercise into a field one. The
readings arrive as remaining thickness at a scatter of points on a plate, not as
a loss, because that is what the meter reads. Turning them into a section takes
two decisions and both are recorded here rather than buried:

* several readings on one plate collapse to the **worst** one, not the mean,
  because the section is checked where it is thinnest;
* a reading thicker than nominal is treated as zero loss rather than as gain,
  since a plate does not put steel back on and the surplus is mill tolerance or
  a dirty probe.

Neither decision is adjustable. A caller who wants a different one is doing a
different job and should say so somewhere this module can see.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from shearstud.errors import GeometryError, RecordError
from shearstud.geometry.section import Section

#: Loss below this is inside the meter's own repeatability and is dropped.
NOISE_FLOOR_IN = 0.005

#: Fraction of nominal thickness whose loss makes a plate a section loss
#: finding rather than a note. Ten percent is where the inspection manual for
#: this inventory starts asking for a rating.
FINDING_THRESHOLD_FRAC = 0.10

#: Fraction at which the plate is reported as severe and the structure moves up
#: the inspection list whatever the rating says.
SEVERE_THRESHOLD_FRAC = 0.25


@dataclass(frozen=True, slots=True)
class ThicknessReading:
    """One ultrasonic reading on one plate.

    ``station_ft`` is the distance along the girder from the near abutment,
    which is how a field sheet records position.
    """

    plate_label: str
    station_ft: float
    remaining_in: float
    measured_on: date

    def __post_init__(self) -> None:
        if not self.plate_label.strip():
            raise RecordError("a thickness reading needs a plate label")
        if self.remaining_in <= 0.0:
            raise RecordError(
                f"{self.plate_label} at {self.station_ft}: "
                f"remaining thickness {self.remaining_in} is not a thickness"
            )
        if self.station_ft < 0.0:
            raise RecordError(f"{self.plate_label}: station {self.station_ft} is behind the datum")


def nominal_thickness_in(section: Section, plate_label: str) -> float:
    """The thinner dimension of a plate, which is the one corrosion attacks."""
    plate = section.plate(plate_label)
    return min(plate.width_in, plate.height_in)


def worst_loss_by_plate(section: Section, readings: Iterable[ThicknessReading]) -> dict[str, float]:
    """Collapse readings to one loss per plate, keeping the worst.

    Plates with no reading are absent from the result rather than present with
    zero, so a caller can tell "measured and sound" from "not measured".
    """
    worst: dict[str, float] = {}
    for reading in readings:
        nominal_in = nominal_thickness_in(section, reading.plate_label)
        loss_in = max(0.0, nominal_in - reading.remaining_in)
        if loss_in < NOISE_FLOOR_IN:
            loss_in = 0.0
        if loss_in > worst.get(reading.plate_label, -1.0):
            worst[reading.plate_label] = loss_in
    return worst


def apply_loss(section: Section, loss_by_plate: Mapping[str, float]) -> Section:
    """Return the section with each named plate thinned by its loss.

    Plate positions are left alone. A corroded flange sits where it always did;
    it is the neutral axis that moves, and it moves because the areas changed.
    """
    known = {p.label for p in section}
    unknown = sorted(set(loss_by_plate) - known)
    if unknown:
        raise GeometryError(f"{section.label}: no plate labelled {unknown[0]!r}")
    thinned = [p.thinned_by(loss_by_plate.get(p.label, 0.0)) for p in section]
    return section.with_plates(thinned)


def measured_section(section: Section, readings: Iterable[ThicknessReading]) -> Section:
    """Readings straight through to a reduced section, the usual entry point."""
    return apply_loss(section, worst_loss_by_plate(section, readings))


@dataclass(frozen=True, slots=True)
class LossFinding:
    """What one plate lost, and how bad that is."""

    plate_label: str
    nominal_in: float
    loss_in: float

    @property
    def remaining_frac(self) -> float:
        """Share of the nominal thickness still there."""
        return (self.nominal_in - self.loss_in) / self.nominal_in

    @property
    def loss_frac(self) -> float:
        """Share of the nominal thickness gone."""
        return self.loss_in / self.nominal_in

    @property
    def is_finding(self) -> bool:
        """True once the loss is worth writing on the inspection report."""
        return self.loss_frac >= FINDING_THRESHOLD_FRAC

    @property
    def is_severe(self) -> bool:
        """True once the loss moves the structure up the list on its own."""
        return self.loss_frac >= SEVERE_THRESHOLD_FRAC


def findings(section: Section, readings: Iterable[ThicknessReading]) -> list[LossFinding]:
    """One finding per measured plate, worst first."""
    worst = worst_loss_by_plate(section, readings)
    out = [
        LossFinding(
            plate_label=label,
            nominal_in=nominal_thickness_in(section, label),
            loss_in=loss_in,
        )
        for label, loss_in in worst.items()
    ]
    out.sort(key=lambda f: (-f.loss_frac, f.plate_label))
    return out


def remaining_capacity_frac(section: Section, readings: Iterable[ThicknessReading]) -> float:
    """Share of the bottom fibre section modulus left after the loss.

    Reported against the bottom fibre because that is where a positive moment
    rating is decided and where the corrosion usually is, the bottom flange
    being under the leaking joint.
    """
    before = section.section_modulus_bottom_in3
    after = measured_section(section, readings).section_modulus_bottom_in3
    return after / before
