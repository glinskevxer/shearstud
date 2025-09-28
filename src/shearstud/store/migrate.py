"""Applying migrations, and refusing to run against a book that has diverged.

The runner is deliberately dull. It applies migrations in order, one
transaction each, and records the version, the name, a digest of the statements
it ran and when it ran them. There is no down migration and there will not be
one: reversing a schema change on a book of record that has been read from is
not a schema problem, it is a data problem, and it wants a new migration that
says what to do with the data.

The digest is the part that earns its keep. A migration that has been applied
somewhere is frozen, and a book whose recorded digest for version three does not
match the version three in the code has been through a different version three.
Refusing on that is the difference between a confusing failure now and an
unexplainable one in six months.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

from shearstud.errors import MigrationError
from shearstud.store import db
from shearstud.store.migrations import MIGRATIONS

#: The table the runner keeps its own record in.
VERSION_TABLE = "schema_version"

_CREATE_VERSION_TABLE = f"""
CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    digest      TEXT NOT NULL,
    applied_at  TEXT NOT NULL
)
"""


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    """One row of the version table."""

    version: int
    name: str
    digest: str
    applied_at: str


def digest_of(migration: ModuleType) -> str:
    """Stable digest of a migration's statements.

    Whitespace is normalised so that reformatting the SQL does not read as a
    change, and nothing else is. A renamed column is a change.
    """
    normalised = " ".join(str(migration.UP).split())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def available() -> list[ModuleType]:
    """Every migration the code knows about, in version order."""
    ordered = sorted(MIGRATIONS, key=lambda m: int(m.VERSION))
    versions = [int(m.VERSION) for m in ordered]
    if versions != list(range(1, len(versions) + 1)):
        raise MigrationError(f"migration versions are {versions}, not a run from one")
    return ordered


def applied(path: Path | str) -> list[AppliedMigration]:
    """What the book says has been applied to it, in version order."""
    if not Path(path).exists():
        return []
    if VERSION_TABLE not in db.table_names(path):
        return []
    rows = db.fetch_all(
        path,
        f"SELECT version, name, digest, applied_at FROM {VERSION_TABLE} ORDER BY version",
    )
    return [
        AppliedMigration(
            version=int(row["version"]),
            name=str(row["name"]),
            digest=str(row["digest"]),
            applied_at=str(row["applied_at"]),
        )
        for row in rows
    ]


def current_version(path: Path | str) -> int:
    """Highest version applied, or zero for a book that has never been touched."""
    rows = applied(path)
    return rows[-1].version if rows else 0


def pending(path: Path | str) -> list[ModuleType]:
    """Migrations the book has not seen yet."""
    seen = current_version(path)
    return [m for m in available() if int(m.VERSION) > seen]


def check_digests(path: Path | str) -> None:
    """Refuse a book whose applied migrations are not the ones in the code."""
    by_version = {int(m.VERSION): m for m in available()}
    for row in applied(path):
        migration = by_version.get(row.version)
        if migration is None:
            raise MigrationError(
                f"the book has version {row.version} ({row.name}) applied and the "
                f"code does not have it"
            )
        expected = digest_of(migration)
        if expected != row.digest:
            raise MigrationError(
                f"version {row.version} ({row.name}) was applied from a different "
                f"migration than the one in this code"
            )


def upgrade(path: Path | str) -> list[int]:
    """Bring a book up to the newest schema, returning the versions applied."""
    with db.transaction(path) as connection:
        connection.execute(_CREATE_VERSION_TABLE)
    check_digests(path)
    done: list[int] = []
    for migration in pending(path):
        version = int(migration.VERSION)
        with db.transaction(path) as connection:
            connection.executescript(str(migration.UP))
            connection.execute(
                f"INSERT INTO {VERSION_TABLE} (version, name, digest, applied_at) "
                f"VALUES (?, ?, ?, ?)",
                (
                    version,
                    str(migration.NAME),
                    digest_of(migration),
                    datetime.now(UTC).isoformat(timespec="seconds"),
                ),
            )
        done.append(version)
    return done


def is_current(path: Path | str) -> bool:
    """True when the book has every migration the code knows about."""
    return not pending(path)


def newest_version() -> int:
    """The version a fresh book comes out at."""
    return int(available()[-1].VERSION)
