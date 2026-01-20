"""Write ``migrations.lock`` from the migrations in the code.

Separate from the check on purpose. A check that repaired what it found would
put the repair in the working tree and out of the diff, and the whole value of
the lock is that changing it is a deliberate line in a commit somebody reads.

``--check`` prints whether the file on disk already matches and changes nothing,
which is the form CI runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

from shearstud.tools.check_migrations import LOCK_PATH, lock_text


def write(path: Path | None = None) -> bool:
    """Write the lock, returning whether anything changed."""
    target = path or LOCK_PATH
    wanted = lock_text()
    if target.exists() and target.read_text(encoding="utf-8") == wanted:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(wanted, encoding="utf-8", newline="\n")
    return True


def is_current(path: Path | None = None) -> bool:
    """Whether the file on disk already says what it should."""
    target = path or LOCK_PATH
    if not target.exists():
        return False
    return target.read_text(encoding="utf-8") == lock_text()


def main(argv: list[str] | None = None) -> int:
    """Write the lock, or check it when asked."""
    args = sys.argv[1:] if argv is None else argv
    if "--check" in args:
        if is_current():
            print(f"build_lock: {LOCK_PATH.name} is current")
            return 0
        print(f"build_lock: {LOCK_PATH.name} is out of date, run build_lock")
        return 1
    changed = write()
    print(f"build_lock: {'rewrote' if changed else 'left'} {LOCK_PATH.name}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
