"""The architecture page: the layers, what is in them, and what they may import.

Read out of the same table ``check_layers`` enforces, so the page and the check
cannot disagree. A page that described a layering the build did not enforce
would be worse than no page, because a reader would trust it.

The module list carries a line count per layer. It is a crude number and it is
the one that answers "where is this package's weight", which is the question
somebody opening it for the first time actually has.
"""

from __future__ import annotations

import sys

from shearstud.tools.check_layers import ALLOWED, FOUNDATION
from shearstud.tools.check_sql import statement_count
from shearstud.tools.generated import Document, run, table
from shearstud.tools.walk import source_files

#: Where this document goes.
DOCUMENT = Document(filename="architecture.md", command="build_architecture")

#: The order the layers are described in, bottom up.
LAYER_ORDER = (
    "",
    "geometry",
    "loads",
    "signals",
    "fatigue",
    "structure",
    "rating",
    "program",
    "store",
    "analysis",
    "cli",
    "tools",
)

#: One line about what each layer is for.
LAYER_PURPOSE = {
    "": "units, the error tree, and nothing that knows about a bridge",
    "geometry": "plates, sections, composite stages and section loss",
    "loads": "vehicles, influence lines, distribution and the dynamic allowance",
    "signals": "strain records, conditioning, defects, rainflow and spectra",
    "fatigue": "detail categories, Miner damage, remaining life and evaluation",
    "structure": "the inventory: identity, spans, girders, details and gauges",
    "rating": "capacity, load factors, the rating equation, posting and permits",
    "program": "what the office does with the numbers: intervals and priority",
    "store": "the book of record, its migrations and its repositories",
    "analysis": "dead load, and the runs that use everything below at once",
    "cli": "the command line, which is how anyone outside the package uses it",
    "tools": "the repository's own checks and generated documents",
}


def layer_rows() -> list[list[str]]:
    """One row per layer: modules, lines and what it is for."""
    counts: dict[str, tuple[int, int]] = {}
    for source in source_files(include_tools=True):
        modules, lines = counts.get(source.layer, (0, 0))
        counts[source.layer] = (modules + 1, lines + len(source.lines()))
    rows = []
    for layer in LAYER_ORDER:
        modules, lines = counts.get(layer, (0, 0))
        if modules == 0:
            continue
        rows.append(
            [
                layer or "(top level)",
                f"{modules}",
                f"{lines}",
                LAYER_PURPOSE.get(layer, ""),
            ]
        )
    return rows


def import_rows() -> list[list[str]]:
    """One row per layer: what it is allowed to import."""
    rows = []
    for layer in LAYER_ORDER:
        if layer not in ALLOWED:
            continue
        allowed = ALLOWED[layer]
        rows.append(
            [
                layer or "(top level)",
                ", ".join(sorted(allowed)) if allowed else "nothing above the foundation",
            ]
        )
    return rows


def module_rows(layer: str) -> list[list[str]]:
    """One row per module in a layer."""
    rows = []
    for source in source_files(include_tools=True):
        if source.layer != layer or source.path.name == "__init__.py":
            continue
        first = (source.text.lstrip().splitlines() or [""])[0].strip('"').strip()
        rows.append([f"`{source.module}`", f"{len(source.lines())}", first])
    return rows


def body() -> str:
    """The whole document."""
    foundation = ", ".join(f"`{name}`" for name in sorted(FOUNDATION))
    parts = [
        "# Architecture",
        "",
        "Imports run one way. A layer may use anything below it and nothing above",
        f"it. Every layer may use the foundation: {foundation}.",
        "",
        "`check_layers` enforces the table below, and this page is generated from",
        "the same table, so the two cannot drift apart.",
        "",
        "## Layers",
        "",
        table(["Layer", "Modules", "Lines", "What it is for"], layer_rows()),
        "",
        "## What each layer may import",
        "",
        table(["Layer", "May import"], import_rows()),
        "",
        f"The package holds {statement_count()} SQL statements, all of them in the",
        "store layer. `check_sql` enforces that.",
        "",
        "## Modules",
        "",
    ]
    for layer in LAYER_ORDER:
        rows = module_rows(layer)
        if not rows:
            continue
        parts.append(f"### {layer or '(top level)'}")
        parts.append("")
        parts.append(table(["Module", "Lines", "What it is"], rows))
        parts.append("")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    """Write or check the architecture page."""
    return run(DOCUMENT, body(), argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
