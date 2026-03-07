"""The inspection programme's own row for each structure.

Everything else in this package is either what the drawings say or what an
analysis concluded. This is neither. It is what an inspector wrote down on a
visit and what the traffic section counted, and it is the only thing in the book
that is overwritten rather than appended, because there is no such thing as last
year's current condition rating.

A structure with no row here is not an error. It is a structure nobody has
inspected under this programme yet, and the ranking has to be able to say so
rather than assume a rating.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from shearstud.errors import StorageError
from shearstud.program.interval import (
    MAX_CONDITION_RATING,
    MIN_CONDITION_RATING,
    StructureState,
)
from shearstud.program.priority import Candidate
from shearstud.store import db

#: Every column a programme row is built from, named rather than starred so
#: that adding one cannot change what a read comes back with.
PROGRAMME_COLUMNS = (
    "structure_number, lowest_condition_rating, daily_traffic, detour_mi, "
    "is_posted, last_inspected, updated_on"
)


@dataclass(frozen=True, slots=True)
class ProgrammeRow:
    """What the office currently believes about one structure."""

    structure_number: str
    lowest_condition_rating: int
    daily_traffic: int
    detour_mi: float
    is_posted: bool
    last_inspected: date
    updated_on: date

    def __post_init__(self) -> None:
        if not self.structure_number.strip():
            raise StorageError("a programme row needs a structure number")
        if not MIN_CONDITION_RATING <= self.lowest_condition_rating <= MAX_CONDITION_RATING:
            raise StorageError(
                f"{self.structure_number}: condition rating "
                f"{self.lowest_condition_rating} is outside "
                f"{MIN_CONDITION_RATING} to {MAX_CONDITION_RATING}"
            )
        if self.daily_traffic < 0:
            raise StorageError(f"{self.structure_number}: traffic {self.daily_traffic} is negative")
        if self.detour_mi < 0.0:
            raise StorageError(
                f"{self.structure_number}: a detour of {self.detour_mi} miles is not a detour"
            )
        if self.updated_on < self.last_inspected:
            raise StorageError(
                f"{self.structure_number}: the row was written on {self.updated_on}, "
                f"before the {self.last_inspected} inspection it describes"
            )

    def state(self, fatigue_life_years: float, *, nonredundant: bool = False) -> StructureState:
        """Turn the row into what the interval rule asks for.

        The fatigue life is not stored here. It comes out of an evaluation run
        and it changes whenever a new campaign is counted, so keeping a copy of
        it in this table would mean two answers to the same question.
        """
        return StructureState(
            lowest_condition_rating=self.lowest_condition_rating,
            is_posted=self.is_posted,
            has_nonredundant_members=nonredundant,
            fatigue_life_years=fatigue_life_years,
        )

    def candidate(
        self, rating_factor: float, fatigue_life_years: float, *, nonredundant: bool = False
    ) -> Candidate:
        """Turn the row into something the ranking can order."""
        return Candidate(
            number=self.structure_number,
            state=self.state(fatigue_life_years, nonredundant=nonredundant),
            rating_factor=rating_factor,
            daily_traffic=self.daily_traffic,
            detour_mi=self.detour_mi,
        )


def _row_to_record(row: sqlite3.Row) -> ProgrammeRow:
    return ProgrammeRow(
        structure_number=str(row["structure_number"]),
        lowest_condition_rating=int(row["lowest_condition_rating"]),
        daily_traffic=int(row["daily_traffic"]),
        detour_mi=float(row["detour_mi"]),
        is_posted=bool(row["is_posted"]),
        last_inspected=date.fromisoformat(str(row["last_inspected"])),
        updated_on=date.fromisoformat(str(row["updated_on"])),
    )


def save(path: Path | str, row: ProgrammeRow) -> None:
    """Write the current facts for a structure, replacing what was there.

    An update rather than a delete and insert. The two look the same from
    outside and behave very differently the day this table gets a child.
    """
    db.execute(
        path,
        "INSERT INTO programme (structure_number, lowest_condition_rating, daily_traffic, "
        "detour_mi, is_posted, last_inspected, updated_on) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (structure_number) DO UPDATE SET "
        "lowest_condition_rating = excluded.lowest_condition_rating, "
        "daily_traffic = excluded.daily_traffic, "
        "detour_mi = excluded.detour_mi, "
        "is_posted = excluded.is_posted, "
        "last_inspected = excluded.last_inspected, "
        "updated_on = excluded.updated_on",
        (
            row.structure_number,
            row.lowest_condition_rating,
            row.daily_traffic,
            row.detour_mi,
            int(row.is_posted),
            row.last_inspected.isoformat(),
            row.updated_on.isoformat(),
        ),
    )


def load(path: Path | str, number: str) -> ProgrammeRow:
    """The row for one structure."""
    found = db.fetch_one(
        path,
        f"SELECT {PROGRAMME_COLUMNS} FROM programme WHERE structure_number = ?",
        (number,),
    )
    if found is None:
        raise StorageError(f"no programme row for {number}")
    return _row_to_record(found)


def find(path: Path | str, number: str) -> ProgrammeRow | None:
    """The row for one structure, or nothing if it has never been inspected."""
    try:
        return load(path, number)
    except StorageError:
        return None


def load_all(path: Path | str) -> list[ProgrammeRow]:
    """Every structure the programme knows about, by number."""
    rows = db.fetch_all(
        path,
        f"SELECT {PROGRAMME_COLUMNS} FROM programme ORDER BY structure_number",
    )
    return [_row_to_record(row) for row in rows]


def uninspected(path: Path | str) -> list[str]:
    """Structures in the book with no programme row, which is the gap.

    A ranking built from ``load_all`` silently leaves these out, and a silent
    omission from a worklist is how a bridge goes ten years without a visit.
    """
    rows = db.fetch_all(
        path,
        "SELECT number FROM structures WHERE number NOT IN "
        "(SELECT structure_number FROM programme) ORDER BY number",
    )
    return [str(row["number"]) for row in rows]


def due_before(path: Path | str, cutoff: date) -> list[ProgrammeRow]:
    """Rows last inspected before a date, oldest first.

    A crude filter on the inspection date rather than on the interval, because
    the interval needs a fatigue life this table does not hold. It narrows the
    list the caller then has to work out properly.
    """
    rows = db.fetch_all(
        path,
        f"SELECT {PROGRAMME_COLUMNS} FROM programme WHERE last_inspected < ? "
        "ORDER BY last_inspected, structure_number",
        (cutoff.isoformat(),),
    )
    return [_row_to_record(row) for row in rows]


def delete(path: Path | str, number: str) -> None:
    """Forget a structure's programme row."""
    db.execute(path, "DELETE FROM programme WHERE structure_number = ?", (number,))
