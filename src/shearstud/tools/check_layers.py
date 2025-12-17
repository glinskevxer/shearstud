"""Imports run one way through the package, and this is where that is written.

The layers, from the bottom up:

    units, errors -> geometry -> loads, signals -> fatigue, structure
                  -> rating -> store -> analysis -> cli

A layer may import from anything below it and from nothing above it. That is the
whole rule, and it is worth enforcing rather than intending because the two
places it wants to break are the two places it would hurt most: geometry
reaching into store to look a section up, and rating reaching into cli to print
something.

Siblings are allowed to import each other where the table says so, and where it
does not, they are not. ``loads`` and ``signals`` are siblings with nothing to
say to each other: a strain record has no business knowing about an axle train,
and the day it does the fatigue layer has been skipped.
"""

from __future__ import annotations

import sys
from typing import Final

from shearstud.tools.walk import imported_modules, report, source_files

#: What each layer is allowed to import from. A layer not listed here may import
#: from nothing but the two at the bottom.
ALLOWED: Final[dict[str, frozenset[str]]] = {
    "": frozenset(),
    "geometry": frozenset(),
    "loads": frozenset({"geometry"}),
    "signals": frozenset({"geometry"}),
    "fatigue": frozenset({"geometry", "signals"}),
    "structure": frozenset({"geometry", "signals", "fatigue"}),
    "rating": frozenset({"geometry", "loads", "signals", "fatigue", "structure"}),
    "store": frozenset({"geometry", "loads", "signals", "fatigue", "structure", "rating"}),
    "analysis": frozenset(
        {"geometry", "loads", "signals", "fatigue", "structure", "rating", "store"}
    ),
    "cli": frozenset(
        {"geometry", "loads", "signals", "fatigue", "structure", "rating", "store", "analysis"}
    ),
    "tools": frozenset(
        {
            "geometry",
            "loads",
            "signals",
            "fatigue",
            "structure",
            "rating",
            "store",
            "analysis",
            "cli",
        }
    ),
}

#: Modules every layer may import, because they are the bottom of the stack.
FOUNDATION: Final[frozenset[str]] = frozenset({"shearstud", "shearstud.units", "shearstud.errors"})


def _layer_of(module: str) -> str:
    """Which layer a dotted module name is in."""
    parts = module.split(".")
    if len(parts) < 3 or parts[0] != "shearstud":
        return ""
    return parts[1]


def problems() -> list[str]:
    """Every import that runs the wrong way through the package."""
    found: list[str] = []
    for source in source_files(include_tools=True):
        layer = source.layer
        if layer not in ALLOWED:
            found.append(f"{source.name} is in layer {layer!r}, which the table does not list")
            continue
        allowed = ALLOWED[layer]
        for imported in sorted(imported_modules(source)):
            if imported in FOUNDATION:
                continue
            other = _layer_of(imported)
            if other in ("", layer):
                continue
            if other not in allowed:
                found.append(f"{source.name} ({layer}) imports {imported} ({other})")
    return found


def orphans() -> list[str]:
    """Layers nothing imports from, which is a different question.

    A layer with no importers is either the top of the stack or dead. The
    command line is the top; anything else on this list wants explaining.
    """
    importers: dict[str, set[str]] = {layer: set() for layer in ALLOWED}
    for source in source_files():
        for imported in imported_modules(source):
            other = _layer_of(imported)
            if other and other != source.layer:
                importers.setdefault(other, set()).add(source.layer)
    return sorted(layer for layer, users in importers.items() if layer and not users)


def main() -> int:
    """Run the check and report."""
    found = problems()
    for layer in orphans():
        if layer not in ("cli", "tools"):
            found.append(f"nothing imports the {layer} layer")
    return report("check_layers", found)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
