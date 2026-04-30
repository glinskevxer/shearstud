"""Finishing the thickness table, which has been in the schema and unused.

``thickness_readings`` arrived with the measurement schema in version two and
nothing has ever written to it. Now that something does, two things it wants
are missing.

A reading needs somewhere to say what the inspector wrote down beside the
number: which side of the web, whether the probe was on a pit or beside one,
whether the section was cleaned first. That is a note, and without it the
information goes on paper and stays there.

And a location measured twice on the same day is one reading recorded twice,
not two readings, so there has to be a way to say that. The unique index is
what makes the write an upsert rather than an append, and it is on the location
and the date together, so the same weld measured again in five years is still a
second row.

The index would fail on a book that already had duplicates. There is no such
book, because nothing has ever written a row here, which is the one advantage
of a table nobody used.
"""

from __future__ import annotations

from typing import Final

VERSION: Final[int] = 5
NAME: Final[str] = "thickness"

UP: Final[str] = """
ALTER TABLE thickness_readings ADD COLUMN note TEXT NOT NULL DEFAULT '';

CREATE UNIQUE INDEX readings_unique_location
    ON thickness_readings (structure_number, girder_id, plate_label, station_ft, measured_on);

CREATE INDEX readings_by_date
    ON thickness_readings (measured_on);
"""
