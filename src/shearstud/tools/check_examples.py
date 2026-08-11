"""The shipped example is load bearing, so it is held to what it is used for.

One JSON document is the structure the README tells a new reader to import, the
one the smoke run takes end to end, and the one four test files read when they
need a real four girder unit rather than a toy. It is not a sample. If it stops
importing, or stops having a cover plate end on it, three separate things break
and none of them says why.

So the checks here are the properties something depends on rather than
everything that could be said about the file. Each one names what would break.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

from shearstud.errors import ShearstudError
from shearstud.store import importer
from shearstud.structure.record import Structure
from shearstud.tools.walk import REPO_ROOT, report

#: Where the examples live.
EXAMPLES: Final[Path] = REPO_ROOT / "examples"

#: Fewest girders an example needs. The distribution equations were fitted
#: against four beams and the smoke run rates through them, so an example with
#: three would exercise the lever rule fallback and not the equations.
MIN_GIRDERS: Final[int] = 4

#: Fewest fatigue details. The fatigue run reports how many of a structure's
#: details nobody has measured, and that line reads as nothing on a structure
#: with one detail on it.
MIN_DETAILS: Final[int] = 4

#: Fewest distinct detail categories. One category means every damage
#: calculation in the example runs down the same branch of the category table.
MIN_CATEGORIES: Final[int] = 2

#: The category the older stringers in this inventory are limited by. An
#: example with nothing worse than a B on it never reaches the branch a real
#: evaluation spends its time in.
WORST_CATEGORY: Final[str] = "E"


def documents() -> list[Path]:
    """Every example document, in name order."""
    if not EXAMPLES.exists():
        return []
    return sorted(EXAMPLES.glob("*.json"))


def problems() -> list[str]:
    """Everything an example is depended on for and does not have."""
    found: list[str] = []
    paths = documents()
    if not paths:
        return [f"there are no examples in {EXAMPLES.name}"]
    for path in paths:
        try:
            structure = importer.read(path)
        except ShearstudError as exc:
            found.append(f"{path.name} does not import: {exc}")
            continue
        found.extend(_check_structure(path.name, structure))
    return found


def _check_structure(name: str, structure: Structure) -> list[str]:
    """What one example has to carry, and why."""
    found: list[str] = []
    if structure.girder_count < MIN_GIRDERS:
        found.append(
            f"{name} has {structure.girder_count} girders; the distribution equations "
            f"want {MIN_GIRDERS} and a smaller example exercises the lever rule instead"
        )
    details = structure.details()
    if len(details) < MIN_DETAILS:
        found.append(
            f"{name} has {len(details)} fatigue details; the coverage line the fatigue "
            f"run prints says nothing on fewer than {MIN_DETAILS}"
        )
    categories = {detail.category_name for detail in details}
    if len(categories) < MIN_CATEGORIES:
        found.append(
            f"{name} carries {len(categories)} detail category; every damage "
            f"calculation on it runs down one branch of the category table"
        )
    if WORST_CATEGORY not in categories:
        found.append(
            f"{name} has no category {WORST_CATEGORY} detail on it, so it never "
            f"reaches the branch a real evaluation spends its time in"
        )
    if not structure.spans.lengths_ft:
        found.append(f"{name} has no spans")
    for girder in structure.girders:
        if abs(girder.length_ft - structure.length_ft) > 1.0e-6:
            found.append(f"{name}: girder {girder.girder_id} is not the length of the unit")
    return found


def summary() -> list[str]:
    """One line per example, for a reader who wants to know what is there."""
    out: list[str] = []
    for path in documents():
        structure = importer.read(path)
        categories = sorted({detail.category_name for detail in structure.details()})
        out.append(
            f"{path.name}: {structure.number}, {structure.girder_count} girders, "
            f"{structure.length_ft:g} ft, {len(structure.details())} details "
            f"in categories {', '.join(categories)}"
        )
    return out


def main(argv: list[str] | None = None) -> int:
    """Run the check and report."""
    args = sys.argv[1:] if argv is None else argv
    if "--list" in args:
        for line in summary():
            print(f"check_examples: {line}")
    return report("check_examples", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
