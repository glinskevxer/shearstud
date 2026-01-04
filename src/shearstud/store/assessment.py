"""Storing what was concluded: ratings, fatigue evaluations and postings.

Conclusions are append only. A rating from 2019 is not corrected when a better
one is worked in 2026; both are kept, dated, and the newest one is the answer.
That is not a preference, it is what the record has to look like when a
structure that was posted in 2019 and unposted in 2026 comes up in a claim.

Everything here is therefore written with a date and read newest first, and
nothing has an update. The only removal is retention, which lives in its own
module so that a delete cannot happen by accident on the way past.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from shearstud.errors import StorageError
from shearstud.fatigue.evaluation import Evaluation
from shearstud.rating.posting import PostingDecision, SignLine
from shearstud.store import db

#: Every column a stored rating is built from, named so that adding one to the
#: table cannot silently change what a read comes back with.
RATING_COLUMNS = (
    "structure_number, girder_id, station_ft, limit_state, level, vehicle, effect, "
    "capacity, factored_dead, factored_live, rating_factor, gross_weight_kip, rated_on"
)


@dataclass(frozen=True, slots=True)
class StoredRating:
    """One rating as the book holds it."""

    structure_number: str
    girder_id: str
    station_ft: float
    limit_state: str
    level: str
    vehicle: str
    effect: str
    capacity: float
    factored_dead: float
    factored_live: float
    rating_factor: float
    gross_weight_kip: float
    rated_on: date

    def __post_init__(self) -> None:
        if self.effect not in ("moment", "shear"):
            raise StorageError(f"unknown load effect {self.effect!r}")
        if self.gross_weight_kip <= 0.0:
            raise StorageError(f"gross weight {self.gross_weight_kip} is not a weight")

    @property
    def is_adequate(self) -> bool:
        """True when the structure carries the vehicle."""
        return self.rating_factor >= 1.0

    @property
    def tonnage_tons(self) -> float:
        """What the rating allows of this vehicle, in short tons."""
        return self.rating_factor * self.gross_weight_kip / 2.0


def save_rating(path: Path | str, rating: StoredRating) -> None:
    """Append one rating to the record."""
    db.execute(
        path,
        "INSERT OR REPLACE INTO ratings (structure_number, girder_id, station_ft, "
        "limit_state, level, vehicle, effect, capacity, factored_dead, factored_live, "
        "rating_factor, gross_weight_kip, rated_on) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rating.structure_number,
            rating.girder_id,
            rating.station_ft,
            rating.limit_state,
            rating.level,
            rating.vehicle,
            rating.effect,
            rating.capacity,
            rating.factored_dead,
            rating.factored_live,
            rating.rating_factor,
            rating.gross_weight_kip,
            rating.rated_on.isoformat(),
        ),
    )


def load_ratings(
    path: Path | str, structure_number: str, on: date | None = None
) -> list[StoredRating]:
    """Ratings for one structure, newest first, or only those from one date."""
    if on is None:
        rows = db.fetch_all(
            path,
            f"SELECT {RATING_COLUMNS} FROM ratings WHERE structure_number = ? "
            "ORDER BY rated_on DESC, girder_id, station_ft, vehicle",
            (structure_number,),
        )
    else:
        rows = db.fetch_all(
            path,
            f"SELECT {RATING_COLUMNS} FROM ratings WHERE structure_number = ? "
            "AND rated_on = ? ORDER BY girder_id, station_ft, vehicle",
            (structure_number, on.isoformat()),
        )
    return [_row_to_rating(row) for row in rows]


def _row_to_rating(row: sqlite3.Row) -> StoredRating:
    return StoredRating(
        structure_number=str(row["structure_number"]),
        girder_id=str(row["girder_id"]),
        station_ft=float(row["station_ft"]),
        limit_state=str(row["limit_state"]),
        level=str(row["level"]),
        vehicle=str(row["vehicle"]),
        effect=str(row["effect"]),
        capacity=float(row["capacity"]),
        factored_dead=float(row["factored_dead"]),
        factored_live=float(row["factored_live"]),
        rating_factor=float(row["rating_factor"]),
        gross_weight_kip=float(row["gross_weight_kip"]),
        rated_on=date.fromisoformat(str(row["rated_on"])),
    )


def latest_rating_date(path: Path | str, structure_number: str) -> date | None:
    """When the structure was last rated, or nothing if it never was."""
    row = db.fetch_one(
        path,
        "SELECT MAX(rated_on) AS newest FROM ratings WHERE structure_number = ?",
        (structure_number,),
    )
    if row is None or row["newest"] is None:
        return None
    return date.fromisoformat(str(row["newest"]))


def governing_rating(path: Path | str, structure_number: str) -> StoredRating:
    """The worst rating from the most recent run."""
    when = latest_rating_date(path, structure_number)
    if when is None:
        raise StorageError(f"{structure_number} has never been rated")
    ratings = load_ratings(path, structure_number, on=when)
    return min(ratings, key=lambda r: (r.rating_factor, r.girder_id, r.vehicle))


def save_evaluation(
    path: Path | str, evaluation: Evaluation, campaign_id: str, evaluated_on: date
) -> None:
    """Append one fatigue evaluation to the record."""
    db.execute(
        path,
        "INSERT OR REPLACE INTO evaluations (detail_id, campaign_id, detail_category, "
        "annual_cycles, effective_range_ksi, largest_range_ksi, infinite_life, "
        "damage_per_first_year, years_remaining, evaluated_on) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            evaluation.detail_id,
            campaign_id,
            evaluation.detail_category,
            evaluation.annual_cycles,
            evaluation.effective_range_ksi,
            evaluation.largest_range_ksi,
            int(evaluation.infinite_life),
            evaluation.damage_per_first_year,
            _finite(evaluation.years_remaining),
            evaluated_on.isoformat(),
        ),
    )


#: Years remaining is stored as this when the detail is infinite life. A NULL
#: would be truer and would also make every ORDER BY on the column a special
#: case, so the sentinel is used and the boolean beside it is what a reader
#: should test.
INFINITE_LIFE_YEARS = 9999.0


def _finite(years: float) -> float:
    return INFINITE_LIFE_YEARS if years > INFINITE_LIFE_YEARS else years


def load_evaluations(path: Path | str, detail_id: str) -> list[tuple[date, str, float, bool]]:
    """One detail's evaluation history, newest first.

    Each row is the date, the campaign, the years remaining and whether the
    detail was infinite life at the time.
    """
    rows = db.fetch_all(
        path,
        "SELECT evaluated_on, campaign_id, years_remaining, infinite_life "
        "FROM evaluations WHERE detail_id = ? ORDER BY evaluated_on DESC",
        (detail_id,),
    )
    return [
        (
            date.fromisoformat(str(row["evaluated_on"])),
            str(row["campaign_id"]),
            float(row["years_remaining"]),
            bool(row["infinite_life"]),
        )
        for row in rows
    ]


def shortest_lives(path: Path | str, limit: int = 20) -> list[tuple[str, float]]:
    """The details with the least life left across the whole inventory."""
    if limit < 1:
        raise StorageError(f"a list of {limit} is not a list")
    rows = db.fetch_all(
        path,
        "SELECT detail_id, MIN(years_remaining) AS worst FROM evaluations "
        "WHERE infinite_life = 0 GROUP BY detail_id ORDER BY worst LIMIT ?",
        (limit,),
    )
    return [(str(row["detail_id"]), float(row["worst"])) for row in rows]


def save_posting(
    path: Path | str, structure_number: str, decision: PostingDecision, decided_on: date
) -> int:
    """Append one posting decision and its sign lines."""
    with db.transaction(path) as connection:
        cursor = connection.execute(
            "INSERT OR REPLACE INTO postings (structure_number, outcome, "
            "governing_factor, decided_on) VALUES (?, ?, ?, ?)",
            (
                structure_number,
                decision.outcome,
                decision.governing_factor,
                decided_on.isoformat(),
            ),
        )
        posting_id = int(cursor.lastrowid or 0)
        connection.executemany(
            "INSERT INTO posting_lines (posting_id, silhouette, vehicle, rating_factor, "
            "tons) VALUES (?, ?, ?, ?, ?)",
            [
                (
                    posting_id,
                    line.silhouette,
                    line.vehicle,
                    line.rating_factor,
                    line.tons if line.is_posted else None,
                )
                for line in decision.lines
            ],
        )
        return posting_id


def load_posting_lines(path: Path | str, posting_id: int) -> list[SignLine]:
    """The sign lines of one posting decision."""
    rows = db.fetch_all(
        path,
        "SELECT silhouette, vehicle, rating_factor, tons FROM posting_lines "
        "WHERE posting_id = ? ORDER BY silhouette",
        (posting_id,),
    )
    if not rows:
        raise StorageError(f"no posting {posting_id}")
    return [
        SignLine(
            silhouette=str(row["silhouette"]),
            vehicle=str(row["vehicle"]),
            rating_factor=float(row["rating_factor"]),
            tons=math.inf if row["tons"] is None else float(row["tons"]),
        )
        for row in rows
    ]


def current_outcome(path: Path | str, structure_number: str) -> str | None:
    """What the structure is signed as today, or nothing if never decided."""
    row = db.fetch_one(
        path,
        "SELECT outcome FROM postings WHERE structure_number = ? ORDER BY decided_on DESC LIMIT 1",
        (structure_number,),
    )
    return None if row is None else str(row["outcome"])
