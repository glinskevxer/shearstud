"""The book of record: one SQLite file, opened and closed around each unit of
work.

Two decisions here shape everything above them.

**A connection is never held open across a call.** Every read and every write
goes through :func:`connect`, which is a context manager, and nothing in this
package keeps a connection on an object. That costs a file open per operation
and buys a guarantee: no half open transaction survives an exception, and no
connection leaks into a garbage collector to be closed at an unpredictable time.
A leaked connection is not a slow leak here, it is a lock nobody can find.

**Foreign keys are on and they are checked.** SQLite defaults them off, per
connection, silently. Turning them on in one place means a delete that would
orphan a row fails at the delete rather than at the next read.

The pragmas are applied on every connection because they are connection scoped,
not database scoped. That is not a detail worth economising on: a single
connection that forgets the foreign key pragma is a connection through which the
schema does not exist.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Final

from shearstud.errors import StorageError

#: Pragmas set on every connection, in order.
CONNECTION_PRAGMAS: Final[tuple[str, ...]] = (
    "PRAGMA foreign_keys = ON",
    "PRAGMA journal_mode = WAL",
    "PRAGMA synchronous = NORMAL",
    "PRAGMA busy_timeout = 5000",
)

#: How long to wait for a lock before giving up, in seconds.
LOCK_TIMEOUT_S: Final[float] = 5.0


@contextmanager
def connect(path: Path | str, *, read_only: bool = False) -> Iterator[sqlite3.Connection]:
    """Open the book of record, and close it whatever happens.

    ``read_only`` opens the file through a URI so a write raises rather than
    succeeding. Every reporting path uses it, which is how a report that
    accidentally mutates gets caught in a test rather than in the field.
    """
    target = Path(path)
    if read_only:
        if not target.exists():
            raise StorageError(f"no book of record at {target}")
        uri = f"file:{target.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=LOCK_TIMEOUT_S)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(target, timeout=LOCK_TIMEOUT_S)
    connection.row_factory = sqlite3.Row
    try:
        for pragma in CONNECTION_PRAGMAS:
            if read_only and pragma.startswith("PRAGMA journal_mode"):
                continue
            connection.execute(pragma)
        yield connection
    finally:
        connection.close()


@contextmanager
def transaction(path: Path | str) -> Iterator[sqlite3.Connection]:
    """A connection that commits on success and rolls back on anything else."""
    with connect(path) as connection:
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        connection.commit()


def fetch_all(path: Path | str, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    """Run one read only query and hand back every row."""
    with connect(path, read_only=True) as connection:
        return list(connection.execute(sql, params))


def fetch_one(path: Path | str, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    """Run one read only query and hand back the first row, or nothing."""
    with connect(path, read_only=True) as connection:
        result: sqlite3.Row | None = connection.execute(sql, params).fetchone()
        return result


def execute(path: Path | str, sql: str, params: tuple[Any, ...] = ()) -> int:
    """Run one write and return how many rows it touched."""
    with transaction(path) as connection:
        cursor = connection.execute(sql, params)
        return cursor.rowcount


def execute_many(path: Path | str, sql: str, rows: list[tuple[Any, ...]]) -> int:
    """Run one write against many parameter sets, all in one transaction."""
    if not rows:
        return 0
    with transaction(path) as connection:
        cursor = connection.executemany(sql, rows)
        return cursor.rowcount


def table_names(path: Path | str) -> list[str]:
    """Every table in the book of record, sorted, internal ones dropped."""
    rows = fetch_all(
        path,
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name",
    )
    return [str(row["name"]) for row in rows]


def foreign_key_violations(path: Path | str) -> list[sqlite3.Row]:
    """Rows that point at something that is not there.

    Should always be empty. It is not empty after a restore from a partial
    backup, which is the one situation this exists for.
    """
    with connect(path, read_only=True) as connection:
        return list(connection.execute("PRAGMA foreign_key_check"))


def integrity_check(path: Path | str) -> list[str]:
    """SQLite's own structural check, as a list of problems."""
    with connect(path, read_only=True) as connection:
        rows = connection.execute("PRAGMA integrity_check").fetchall()
    problems = [str(row[0]) for row in rows]
    return [] if problems == ["ok"] else problems
