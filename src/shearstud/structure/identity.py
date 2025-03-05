"""Structure numbers, as this agency writes them.

A structure number is ``CC-RR-SSSS`` with an optional parallel suffix letter:
county code, route class, four digit sequence, and a letter when there is more
than one structure carrying the same route over the same obstacle. ``18-SH-0473``
and ``18-SH-0473B`` are the northbound and southbound halves of one crossing and
are rated separately, so the suffix is part of the identity and not decoration.

Parsing is strict. The inventory has forty years of hand typed numbers in it and
every lenient parser written for this file has eventually matched something it
should not have, so the only latitude given is case, surrounding whitespace, and
the separator being a dash or a space.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from shearstud.errors import InputError

#: Route classes this agency maintains structures on.
ROUTE_CLASSES: Final[tuple[str, ...]] = ("IH", "US", "SH", "FM", "CR", "PR", "TL")

#: Counties are numbered from one, and the highest one on the books is 64.
MAX_COUNTY_CODE: Final[int] = 64

_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?P<county>\d{2})[-\s](?P<route>[A-Z]{2})[-\s](?P<sequence>\d{4})(?P<parallel>[A-Z]?)$"
)


@dataclass(frozen=True, order=True, slots=True)
class StructureNumber:
    """One structure's identity in the inventory.

    Ordering is county, then route class, then sequence, then parallel suffix,
    which is the order the paper file cabinet is in and therefore the order
    every listing in this package comes out in.
    """

    county_code: int
    route_class: str
    sequence: int
    parallel: str = ""

    def __post_init__(self) -> None:
        if not 1 <= self.county_code <= MAX_COUNTY_CODE:
            raise InputError(f"county code {self.county_code} is outside 1 to {MAX_COUNTY_CODE}")
        if self.route_class not in ROUTE_CLASSES:
            raise InputError(f"unknown route class {self.route_class!r}")
        if not 0 <= self.sequence <= 9999:
            raise InputError(f"sequence {self.sequence} does not fit four digits")
        if self.parallel and not (len(self.parallel) == 1 and self.parallel.isalpha()):
            raise InputError(f"parallel suffix {self.parallel!r} is not a single letter")
        if self.parallel and not self.parallel.isupper():
            raise InputError(f"parallel suffix {self.parallel!r} must be upper case")

    def __str__(self) -> str:
        return f"{self.county_code:02d}-{self.route_class}-{self.sequence:04d}{self.parallel}"

    @property
    def is_parallel(self) -> bool:
        """True when this structure is one of a pair or a set."""
        return bool(self.parallel)

    def sibling(self, parallel: str) -> StructureNumber:
        """The structure alongside this one, carrying a different suffix."""
        if not parallel:
            raise InputError("a sibling needs a parallel suffix")
        return StructureNumber(self.county_code, self.route_class, self.sequence, parallel.upper())

    def without_parallel(self) -> StructureNumber:
        """The crossing this structure belongs to, suffix dropped."""
        return StructureNumber(self.county_code, self.route_class, self.sequence)


def parse(text: str) -> StructureNumber:
    """Parse a structure number, accepting case and dash or space separators."""
    cleaned = " ".join(text.strip().upper().split())
    match = _PATTERN.match(cleaned)
    if match is None:
        raise InputError(f"{text!r} is not a structure number, expected CC-RR-SSSS")
    return StructureNumber(
        county_code=int(match["county"]),
        route_class=match["route"],
        sequence=int(match["sequence"]),
        parallel=match["parallel"],
    )


def try_parse(text: str) -> StructureNumber | None:
    """Parse, or return ``None`` when the text is not a structure number.

    Exists for the import path, which reads spreadsheets full of blank rows and
    header repeats and would otherwise be a try block around every line.
    """
    try:
        return parse(text)
    except InputError:
        return None
