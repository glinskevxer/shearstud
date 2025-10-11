"""Pruning the record, which is the only place anything is deleted on purpose.

Retention is separated from the repositories so that a delete cannot happen on
the way past something else. Everything here is a delete, everything here is
named for what it removes, and every function refuses to remove the newest run
for a structure whatever the cutoff says.

That last rule is the whole design. A cutoff by date alone will quietly retire a
structure that has not been rated since before the cutoff, and the failure shows
up as a structure with no rating at all rather than as an error. Keeping the
newest run unconditionally means a quiet structure loses nothing and a busy one
loses its history and not its answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from shearstud.errors import StorageError
from shearstud.store import db

#: Nothing is pruned inside this many years, whatever a caller asks for. Ten
#: years is the retention the agency's own records policy sets, and a caller
#: that wants less is asking for something this module will not do.
MIN_RETENTION_YEARS = 10


@dataclass(frozen=True, slots=True)
class PruneReport:
    """What a prune removed, per table."""

    ratings: int = 0
    evaluations: int = 0
    postings: int = 0

    @property
    def total(self) -> int:
        """Rows removed altogether."""
        return self.ratings + self.evaluations + self.postings

    @property
    def removed_nothing(self) -> bool:
        """True when the prune was a no operation."""
        return self.total == 0


def check_cutoff(cutoff: date, today: date) -> None:
    """Refuse a cutoff inside the retention policy."""
    years = (today - cutoff).days / 365.25
    if years < MIN_RETENTION_YEARS:
        raise StorageError(
            f"a cutoff of {cutoff} is {years:.1f} years back, inside the "
            f"{MIN_RETENTION_YEARS} year retention policy"
        )


def prune_ratings(path: Path | str, cutoff: date, today: date) -> int:
    """Remove ratings older than the cutoff, keeping each structure's newest run.

    The newest run is kept by structure, not overall, so a structure last rated
    in 1998 keeps its 1998 rating and a structure rated every year keeps only
    the last one from before the cutoff onwards.
    """
    check_cutoff(cutoff, today)
    return db.execute(
        path,
        "DELETE FROM ratings WHERE rated_on < ? AND rated_on <> ("
        "  SELECT MAX(inner.rated_on) FROM ratings AS inner"
        "  WHERE inner.structure_number = ratings.structure_number"
        ")",
        (cutoff.isoformat(),),
    )


def prune_evaluations(path: Path | str, cutoff: date, today: date) -> int:
    """Remove fatigue evaluations older than the cutoff, keeping each detail's
    newest one."""
    check_cutoff(cutoff, today)
    return db.execute(
        path,
        "DELETE FROM evaluations WHERE evaluated_on < ? AND evaluated_on <> ("
        "  SELECT MAX(inner.evaluated_on) FROM evaluations AS inner"
        "  WHERE inner.detail_id = evaluations.detail_id"
        ")",
        (cutoff.isoformat(),),
    )


def prune_postings(path: Path | str, cutoff: date, today: date) -> int:
    """Remove posting decisions older than the cutoff, keeping each structure's
    newest one.

    Superseded postings are the record of what a bridge was signed as on a given
    day, so they are kept longer than anything else and the caller has to say a
    date rather than a count.
    """
    check_cutoff(cutoff, today)
    return db.execute(
        path,
        "DELETE FROM postings WHERE decided_on < ? AND decided_on <> ("
        "  SELECT MAX(inner.decided_on) FROM postings AS inner"
        "  WHERE inner.structure_number = postings.structure_number"
        ")",
        (cutoff.isoformat(),),
    )


def prune(path: Path | str, cutoff: date, today: date) -> PruneReport:
    """Prune all three conclusion tables to one cutoff."""
    return PruneReport(
        ratings=prune_ratings(path, cutoff, today),
        evaluations=prune_evaluations(path, cutoff, today),
        postings=prune_postings(path, cutoff, today),
    )


def orphaned_spectra(path: Path | str) -> list[tuple[str, str]]:
    """Spectra whose gauge has been removed from the structure.

    Should always be empty, because the foreign key cascade takes them. This
    exists to say so after a restore, which is the one route by which they can
    appear.
    """
    rows = db.fetch_all(
        path,
        "SELECT s.campaign_id, s.gauge_id FROM spectra AS s "
        "LEFT JOIN gauges AS g ON g.gauge_id = s.gauge_id "
        "WHERE g.gauge_id IS NULL ORDER BY s.campaign_id, s.gauge_id",
    )
    return [(str(row["campaign_id"]), str(row["gauge_id"])) for row in rows]


def vacuum(path: Path | str) -> None:
    """Rebuild the file so a prune actually gives the disk space back."""
    with db.connect(path) as connection:
        connection.execute("VACUUM")
