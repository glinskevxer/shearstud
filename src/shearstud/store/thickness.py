"""Storing ultrasonic thickness readings, and reading them back as a section.

Readings are append only. A location measured in 2019 and again in 2026 has two
rows, and the point of keeping both is that the pair is a corrosion rate while
either one alone is only a number. Nothing here overwrites.

Reading them back is where the care is. A section reduced by every reading ever
taken would apply a 2019 loss on top of a 2026 one at the same place and produce
a plate thinner than anybody measured, so the read collapses to the newest
reading per location first and only then goes to the geometry.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from shearstud.errors import StorageError
from shearstud.geometry.loss import ThicknessReading, measured_section
from shearstud.geometry.schedule import SectionRun
from shearstud.geometry.section import Section
from shearstud.store import db
from shearstud.structure.girder import GirderLine
from shearstud.structure.record import Structure

#: Every column a stored reading is built from.
READING_COLUMNS = (
    "structure_number, girder_id, plate_label, station_ft, remaining_in, measured_on, note"
)

#: How close two stations have to be to count as the same location, in feet.
#: A field sheet records to the nearest half foot and the same weld gets
#: written down as 24.5 one year and 24.0 the next.
SAME_LOCATION_FT = 1.0


@dataclass(frozen=True, slots=True)
class StoredReading:
    """One ultrasonic reading as the book holds it."""

    structure_number: str
    girder_id: str
    plate_label: str
    station_ft: float
    remaining_in: float
    measured_on: date
    note: str = ""

    def __post_init__(self) -> None:
        if not self.structure_number.strip():
            raise StorageError("a thickness reading needs a structure number")
        if not self.girder_id.strip():
            raise StorageError(f"{self.structure_number}: a reading needs a girder")
        if not self.plate_label.strip():
            raise StorageError(f"{self.structure_number}: a reading needs a plate label")
        if self.remaining_in <= 0.0:
            raise StorageError(
                f"{self.structure_number} {self.girder_id} {self.plate_label}: "
                f"remaining thickness {self.remaining_in} is not a thickness"
            )
        if self.station_ft < 0.0:
            raise StorageError(
                f"{self.structure_number}: station {self.station_ft} is behind the datum"
            )

    def as_reading(self) -> ThicknessReading:
        """The geometry package's view of this row."""
        return ThicknessReading(
            plate_label=self.plate_label,
            station_ft=self.station_ft,
            remaining_in=self.remaining_in,
            measured_on=self.measured_on,
        )

    def is_near(self, other: StoredReading) -> bool:
        """Whether two readings are close enough to be the same place."""
        if self.plate_label != other.plate_label:
            return False
        return abs(self.station_ft - other.station_ft) <= SAME_LOCATION_FT


def _to_record(row: sqlite3.Row) -> StoredReading:
    return StoredReading(
        structure_number=str(row["structure_number"]),
        girder_id=str(row["girder_id"]),
        plate_label=str(row["plate_label"]),
        station_ft=float(row["station_ft"]),
        remaining_in=float(row["remaining_in"]),
        measured_on=date.fromisoformat(str(row["measured_on"])),
        note=str(row["note"]),
    )


def save(path: Path | str, reading: StoredReading) -> None:
    """Append one reading. Measuring the same place again on the same day
    replaces that day's reading and nothing else."""
    db.execute(
        path,
        "INSERT INTO thickness_readings (structure_number, girder_id, plate_label, "
        "station_ft, remaining_in, measured_on, note) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (structure_number, girder_id, plate_label, station_ft, measured_on) "
        "DO UPDATE SET remaining_in = excluded.remaining_in, note = excluded.note",
        (
            reading.structure_number,
            reading.girder_id,
            reading.plate_label,
            reading.station_ft,
            reading.remaining_in,
            reading.measured_on.isoformat(),
            reading.note,
        ),
    )


def load(path: Path | str, number: str, girder_id: str | None = None) -> list[StoredReading]:
    """Every reading on a structure, newest first."""
    if girder_id is None:
        rows = db.fetch_all(
            path,
            f"SELECT {READING_COLUMNS} FROM thickness_readings WHERE structure_number = ? "
            "ORDER BY measured_on DESC, girder_id, plate_label, station_ft",
            (number,),
        )
    else:
        rows = db.fetch_all(
            path,
            f"SELECT {READING_COLUMNS} FROM thickness_readings WHERE structure_number = ? "
            "AND girder_id = ? ORDER BY measured_on DESC, plate_label, station_ft",
            (number, girder_id),
        )
    return [_to_record(row) for row in rows]


def locations(readings: list[StoredReading]) -> list[list[StoredReading]]:
    """Readings grouped into places: one plate, stations within the tolerance.

    Rounding the station into a bucket would be shorter and would be wrong at
    the edges, where two readings a tenth of a foot apart fall either side of a
    boundary and read as different places. Walking the sorted stations and
    breaking whenever the gap exceeds the tolerance has no edges.

    It does chain: readings at 24.0, 24.9 and 25.8 are one location even though
    the first and last are nearly two feet apart. On a field sheet that is the
    right answer, because they are three probe positions on one patch of rust.
    """
    out: list[list[StoredReading]] = []
    ordered = sorted(readings, key=lambda r: (r.plate_label, r.station_ft, r.measured_on))
    for reading in ordered:
        if out and reading.is_near(out[-1][-1]):
            out[-1].append(reading)
        else:
            out.append([reading])
    return out


def newest_per_location(readings: list[StoredReading]) -> list[StoredReading]:
    """One reading per place, the most recent one.

    Without this a section reduced by every reading ever taken applies a 2019
    loss on top of a 2026 one at the same weld and comes out thinner than
    anybody measured.
    """
    out = [max(group, key=lambda r: (r.measured_on, r.station_ft)) for group in locations(readings)]
    return sorted(out, key=lambda r: (r.plate_label, r.station_ft))


def measured(path: Path | str, number: str, girder_id: str, section: Section) -> Section:
    """A girder's section reduced by the newest reading at each location."""
    readings = newest_per_location(load(path, number, girder_id))
    if not readings:
        return section
    return measured_section(section, [row.as_reading() for row in readings])


def has_readings(path: Path | str, number: str, girder_id: str | None = None) -> bool:
    """Whether anybody has put a meter on this structure."""
    return bool(load(path, number, girder_id))


def measured_on_dates(path: Path | str, number: str) -> list[date]:
    """Every day somebody took readings on a structure, newest first."""
    rows = db.fetch_all(
        path,
        "SELECT DISTINCT measured_on FROM thickness_readings WHERE structure_number = ? "
        "ORDER BY measured_on DESC",
        (number,),
    )
    return [date.fromisoformat(str(row["measured_on"])) for row in rows]


def corrosion_rate_in_per_yr(readings: list[StoredReading]) -> float | None:
    """Loss per year at one location, from its oldest and newest readings.

    Nothing when there is only one reading, which is the usual case and is not
    an error. A single reading says how thin the plate is and says nothing at
    all about how fast it got that way.
    """
    if len(readings) < 2:
        return None
    ordered = sorted(readings, key=lambda r: r.measured_on)
    first, last = ordered[0], ordered[-1]
    years = (last.measured_on - first.measured_on).days / 365.25
    if years <= 0.0:
        return None
    return (first.remaining_in - last.remaining_in) / years


def delete(path: Path | str, number: str) -> int:
    """Forget every reading on a structure, returning how many went."""
    return db.execute(path, "DELETE FROM thickness_readings WHERE structure_number = ?", (number,))


def measured_girder(path: Path | str, number: str, girder: GirderLine) -> GirderLine:
    """A girder whose every run is reduced by the readings taken on that run.

    Run by run rather than girder by girder, which matters on any girder with a
    cover plate. The corrosion is under the leaking joint at one end; applying
    its loss to the heavy section over the pier would take a sixteenth off a
    plate nobody has measured and quietly move the rating.
    """
    readings = newest_per_location(load(path, number, girder.girder_id))
    if not readings:
        return girder

    def reduce(run: SectionRun) -> Section:
        on_this_run = [
            row.as_reading()
            for row in readings
            if run.from_station_ft <= row.station_ft <= run.to_station_ft
        ]
        if not on_this_run:
            return run.section
        return measured_section(run.section, on_this_run)

    return girder.with_schedule(girder.schedule.mapped(reduce))


def measured_structure(path: Path | str, structure: Structure) -> Structure:
    """Every girder on a structure reduced by its own readings."""
    number = str(structure.number)
    if not has_readings(path, number):
        return structure
    return structure.with_girders(
        [measured_girder(path, number, girder) for girder in structure.girders]
    )
