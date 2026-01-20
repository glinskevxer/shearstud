"""The glossary, built from the constants the code actually uses.

Every table in this document is read out of the package rather than typed here.
The unit suffixes come from ``units.SUFFIXES``, the detail categories from the
fatigue table, the vehicles from the catalogue and the errors from the error
module. A term added to the code appears in the glossary on the next run, and a
term removed from the code disappears, which is the only way a glossary stays
true for longer than a month.
"""

from __future__ import annotations

import sys

from shearstud.fatigue import categories as cat
from shearstud.loads import vehicles
from shearstud.tools.generated import Document, run, table
from shearstud.units import SUFFIXES

#: Where this document goes.
DOCUMENT = Document(filename="glossary.md", command="build_glossary")


def unit_rows() -> list[list[str]]:
    """One row per registered unit suffix."""
    return [[f"`_{suffix}`", text] for suffix, text in sorted(SUFFIXES.items())]


def category_rows() -> list[list[str]]:
    """One row per fatigue detail category."""
    return [
        [
            detail.name,
            f"{detail.constant_a / 1e8:g} x 10^8",
            f"{detail.threshold_ksi:g}",
            detail.example,
        ]
        for detail in cat.categories()
    ]


def vehicle_rows() -> list[list[str]]:
    """One row per catalogue vehicle."""
    rows = []
    for name in vehicles.names():
        train = vehicles.vehicle(name)
        rows.append(
            [
                name,
                vehicles.vehicle_class(name),
                f"{train.axle_count}",
                f"{train.gross_kip:g}",
                f"{train.length_ft:g}",
            ]
        )
    return sorted(rows, key=lambda row: (row[1], row[0]))


def body() -> str:
    """The whole document."""
    parts = [
        "# Glossary",
        "",
        "Everything below is read out of the package at build time. If a term is",
        "here it is in the code, and if it is in the code it is here.",
        "",
        "## Unit suffixes",
        "",
        "Every number crossing a public boundary carries one of these in its name.",
        "`check_units` enforces it.",
        "",
        table(["Suffix", "Means"], unit_rows()),
        "",
        "## Fatigue detail categories",
        "",
        "AASHTO LRFD Table 6.6.1.2.5-1. The detail constant sets the sloping part",
        "of the S-N curve; the threshold is the constant amplitude fatigue limit.",
        "",
        table(
            ["Category", "Detail constant", "Threshold, ksi", "Example"],
            category_rows(),
        ),
        "",
        "## Vehicles",
        "",
        "The catalogue a rating draws on. Design vehicles are for a design check,",
        "legal and hauling vehicles decide a posting, and emergency vehicles are",
        "rated separately because failing one is a conversation rather than a sign.",
        "",
        table(
            ["Vehicle", "Class", "Axles", "Gross, kip", "Length, ft"],
            vehicle_rows(),
        ),
    ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    """Write or check the glossary."""
    return run(DOCUMENT, body(), argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
