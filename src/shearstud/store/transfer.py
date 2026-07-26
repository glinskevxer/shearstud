"""Moving a whole book somewhere else, and reading one back.

A district hands its book to the central office once a year and the central
office hands one back after a review. Both directions want a file that is not a
SQLite database, because the two ends run different versions of this package and
a database written by a newer schema is a database the older one refuses.

So the transfer format is JSON, one array per table, and it carries the schema
version it was written at. Reading it back into a book at a different version is
refused rather than attempted. That is deliberate and it is the whole reason the
version is in the file: a partial load that silently drops a column nobody
noticed is worse than a refusal somebody has to think about.

This deliberately does not go through the repositories. It is a table copy, and
a table copy that reconstructed every object on the way through would refuse a
row the current validation rejects, which is exactly the row somebody is trying
to move in order to look at it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final

from shearstud.errors import StorageError
from shearstud.store import db, migrate

#: What the transfer file calls itself, so a JSON file that is not one of these
#: is refused before anything is written.
FORMAT: Final[str] = "shearstud-book"

#: Tables carried in the transfer, in the order they load. Parents before
#: children, because the foreign keys are on and a child loaded first is a
#: child with nothing to point at.
TABLES: Final[tuple[str, ...]] = (
    "structures",
    "girders",
    "section_runs",
    "section_plates",
    "details",
    "gauges",
    "campaigns",
    "spectra",
    "spectrum_bins",
    "ratings",
    "evaluations",
    "postings",
    "posting_lines",
    "programme",
    "thickness_readings",
)

#: Functions here that build a statement around an identifier rather than a
#: parameter, because SQLite will not bind one. Every one of them puts the
#: table through :func:`checked_table` first and takes its column names off
#: ``PRAGMA table_info``, so nothing reaches a statement that the live schema
#: did not hand back. ``check_sql`` reads this tuple rather than keeping its
#: own copy.
SQL_NAME_INTERPOLATION = ("columns_of", "dump", "load")

#: The one table that is not carried. It is written by the migration runner and
#: reading somebody else's copy of it would tell this book a migration ran that
#: never did.
NOT_CARRIED: Final[str] = migrate.VERSION_TABLE


def checked_table(table: str) -> str:
    """A table name this module is willing to put in a statement.

    Nothing outside the carried list gets through, so a caller cannot reach a
    table by naming it. The list is a module constant, which means the set of
    names that can ever appear in a statement here is fixed at import.
    """
    if table not in TABLES:
        raise StorageError(f"{table!r} is not a table this transfer carries")
    return table


def columns_of(path: Path | str, table: str) -> list[str]:
    """The column names of a table, in declaration order."""
    rows = db.fetch_all(path, f"PRAGMA table_info({checked_table(table)})")
    if not rows:
        raise StorageError(f"no table {table!r} in this book")
    return [str(row["name"]) for row in rows]


def dump(path: Path | str) -> dict[str, Any]:
    """A whole book as a document."""
    version = migrate.current_version(path)
    if version == 0:
        raise StorageError("this book has no schema, so there is nothing to move")
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in TABLES:
        names = columns_of(path, table)
        listed = ", ".join(names)
        rows = db.fetch_all(path, f"SELECT {listed} FROM {checked_table(table)}")
        tables[table] = [{name: row[name] for name in names} for row in rows]
    return {"format": FORMAT, "schema_version": version, "tables": tables}


def load(path: Path | str, document: dict[str, Any]) -> dict[str, int]:
    """Write a document into an empty book, returning what went into each table.

    The book has to be empty. Merging two books is a different job with its own
    questions about which copy of a structure wins, and answering those quietly
    inside a load is how one of them disappears.
    """
    _check_document(document)
    version = migrate.current_version(path)
    if version != int(document["schema_version"]):
        raise StorageError(
            f"the file was written at schema {document['schema_version']} and this "
            f"book is at {version}; upgrade one of them first"
        )
    for table in TABLES:
        if db.row_count(path, table) > 0:
            raise StorageError(f"this book already has rows in {table}")

    written: dict[str, int] = {}
    with db.transaction(path) as connection:
        for table in TABLES:
            rows = document["tables"].get(table, [])
            if not rows:
                written[table] = 0
                continue
            names = list(rows[0])
            listed = ", ".join(names)
            marks = ", ".join("?" * len(names))
            connection.executemany(
                f"INSERT INTO {checked_table(table)} ({listed}) VALUES ({marks})",
                [tuple(row[name] for name in names) for row in rows],
            )
            written[table] = len(rows)
    return written


def _check_document(document: dict[str, Any]) -> None:
    """Refuse anything that is not one of these files."""
    if document.get("format") != FORMAT:
        raise StorageError(f"this is not a {FORMAT} file")
    if "schema_version" not in document:
        raise StorageError("the file does not say what schema it was written at")
    tables = document.get("tables")
    if not isinstance(tables, dict):
        raise StorageError("the file carries no tables")
    unknown = sorted(set(tables) - set(TABLES))
    if unknown:
        raise StorageError(f"the file carries tables this version does not have: {unknown}")


def write(path: Path | str, book: Path | str) -> int:
    """Dump a book to a file, returning how many rows it carried."""
    document = dump(book)
    Path(path).write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
    return row_count(document)


def read(path: Path | str) -> dict[str, Any]:
    """A transfer document off disk."""
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StorageError(f"{source.name} is not readable JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise StorageError(f"{source.name} is not a {FORMAT} file")
    _check_document(document)
    return document


def row_count(document: dict[str, Any]) -> int:
    """How many rows a document carries altogether."""
    return sum(len(rows) for rows in document["tables"].values())
