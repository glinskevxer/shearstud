"""The facts the inspection programme runs on, none of which are engineering.

Condition ratings, traffic counts and detour lengths come off the inspection
report and out of the traffic section, they change on their own schedule, and
none of them is derivable from anything already in the book. They get their own
table rather than more columns on ``structures`` because a structure row is
written by an import of the drawings and this row is written by an inspector.

One row per structure, replaced in place. This is a statement of what is
currently true rather than a record of what was concluded, so unlike ratings and
evaluations it is not append only.
"""

from __future__ import annotations

from typing import Final

VERSION: Final[int] = 4
NAME: Final[str] = "programme"

UP: Final[str] = """
CREATE TABLE programme (
    structure_number         TEXT PRIMARY KEY
                             REFERENCES structures(number) ON DELETE CASCADE,
    lowest_condition_rating  INTEGER NOT NULL
                             CHECK (lowest_condition_rating BETWEEN 0 AND 9),
    daily_traffic            INTEGER NOT NULL CHECK (daily_traffic >= 0),
    detour_mi                REAL NOT NULL CHECK (detour_mi >= 0),
    is_posted                INTEGER NOT NULL CHECK (is_posted IN (0, 1)),
    last_inspected           TEXT NOT NULL,
    updated_on               TEXT NOT NULL
);

CREATE INDEX programme_by_condition
    ON programme (lowest_condition_rating);

CREATE INDEX programme_by_inspection
    ON programme (last_inspected);
"""
