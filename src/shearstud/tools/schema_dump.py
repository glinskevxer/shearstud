"""The schema as SQLite itself reports it, after every migration has run.

Not the migration text. The migrations are a sequence of changes and the schema
is what they add up to, and reading a five migration sequence to work out what a
column ends up called is exactly the thing this document exists to save.

The dump is taken from a throwaway book built in a temporary directory, so it is
the real schema an upgrade produces rather than a transcription of one.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from shearstud.store import db, migrate
from shearstud.tools.generated import Document, run, table

#: Where this document goes.
DOCUMENT = Document(filename="schema.md", command="schema_dump")

#: Objects SQLite keeps for itself.
INTERNAL_PREFIX = "sqlite_"

#: ``PRAGMA`` takes a table name as an identifier and will not bind it, so the
#: three readers below build it into the statement. Every one of them is handed
#: a name that came from ``table_names`` on the same book, so a caller cannot
#: get an arbitrary string past them.
SQL_NAME_INTERPOLATION = ("columns_of", "indexes_of", "foreign_keys_of")


def _fresh_book(directory: Path) -> Path:
    path = directory / "schema.sqlite3"
    migrate.upgrade(path)
    return path


def table_names(path: Path) -> list[str]:
    """Every table an upgraded book holds, sorted."""
    return [name for name in db.table_names(path) if not name.startswith(INTERNAL_PREFIX)]


def columns_of(path: Path, name: str) -> list[list[str]]:
    """One row per column: name, type, whether it may be null, and its default."""
    with db.connect(path, read_only=True) as connection:
        rows = connection.execute(f"PRAGMA table_info({name})").fetchall()
    out = []
    for row in rows:
        default = "" if row["dflt_value"] is None else str(row["dflt_value"])
        key = " primary" if row["pk"] else ""
        out.append(
            [
                str(row["name"]),
                str(row["type"]) + key,
                "no" if row["notnull"] else "yes",
                default,
            ]
        )
    return out


def indexes_of(path: Path, name: str) -> list[list[str]]:
    """One row per index on a table."""
    with db.connect(path, read_only=True) as connection:
        rows = connection.execute(f"PRAGMA index_list({name})").fetchall()
        out = []
        for row in rows:
            index_name = str(row["name"])
            if index_name.startswith(INTERNAL_PREFIX):
                continue
            members = connection.execute(f"PRAGMA index_info({index_name})").fetchall()
            columns = ", ".join(str(member["name"]) for member in members)
            out.append([index_name, "yes" if row["unique"] else "no", columns])
    return out


def foreign_keys_of(path: Path, name: str) -> list[list[str]]:
    """One row per foreign key on a table."""
    with db.connect(path, read_only=True) as connection:
        rows = connection.execute(f"PRAGMA foreign_key_list({name})").fetchall()
    return [
        [str(row["from"]), f"{row['table']}.{row['to']}", str(row["on_delete"])] for row in rows
    ]


def _sections(path: Path) -> list[str]:
    out: list[str] = []
    for name in table_names(path):
        out.append(f"### `{name}`")
        out.append("")
        out.append(table(["Column", "Type", "Null", "Default"], columns_of(path, name)))
        out.append("")
        keys = foreign_keys_of(path, name)
        if keys:
            out.append(table(["Column", "References", "On delete"], keys))
            out.append("")
        indexes = indexes_of(path, name)
        if indexes:
            out.append(table(["Index", "Unique", "Columns"], indexes))
            out.append("")
    return out


def body() -> str:
    """The whole document, from a book built for the purpose."""
    with tempfile.TemporaryDirectory() as directory:
        path = _fresh_book(Path(directory))
        names = table_names(path)
        parts = [
            "# Schema",
            "",
            f"What migration {migrate.newest_version()} leaves behind, read back out",
            "of SQLite rather than transcribed from the migration text.",
            "",
            f"{len(names)} tables: " + ", ".join(f"`{name}`" for name in names) + ".",
            "",
            "## Tables",
            "",
            *_sections(path),
        ]
        return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    """Write or check the schema page."""
    return run(DOCUMENT, body(), argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
