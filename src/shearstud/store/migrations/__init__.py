"""Numbered schema migrations, applied in order and never edited afterwards.

Each migration is a module named ``mNNN_something`` holding a ``VERSION``, a
``NAME`` and an ``UP`` statement block. They are discovered by import rather
than by scanning the directory, so a migration that is not listed here does not
run, and a listed one that does not exist fails at import rather than at the
first upgrade of a production book.

A migration that has been applied anywhere is frozen. Editing one changes its
digest, and ``check_migrations`` compares every digest against
``migrations.lock`` and fails the build. The remedy for a wrong migration is
always another migration.
"""

from __future__ import annotations

from types import ModuleType

from shearstud.store.migrations import m001_structures, m002_measurement, m003_assessment

#: Every migration, in the order they apply.
MIGRATIONS: tuple[ModuleType, ...] = (
    m001_structures,
    m002_measurement,
    m003_assessment,
)

__all__ = ["MIGRATIONS"]
