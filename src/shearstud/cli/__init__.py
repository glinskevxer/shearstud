"""The command line surface.

The command modules are imported here for their side effect: each one attaches
its commands to the group in ``main``. Importing ``shearstud.cli`` therefore
gives a complete command line, and importing ``shearstud.cli.main`` alone gives
the bare group, which is what the tests that check registration want.
"""

from __future__ import annotations

from shearstud.cli import measurement, program, rating, structures  # noqa: F401
from shearstud.cli.main import main, run

__all__ = ["main", "run"]
