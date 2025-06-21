"""Fatigue details: where they are, what category they are, and what watches
them.

A detail is a place on a girder where a weld, an attachment or a plate end
concentrates stress. It carries a station, a category, and the fibre it is on,
because a detail on the bottom flange and one on the top flange of the same
section see opposite signs and very different ranges.

The gauge link is deliberately loose. A detail may have no gauge on it, which is
the normal case, and then its stress range is computed rather than measured. A
detail may have more than one gauge, when a rosette or a redundant channel was
installed. Nothing here assumes a one to one pairing, because on this inventory
it has never been one.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Final

from shearstud.errors import ConfigError, InputError
from shearstud.fatigue.categories import DetailCategory, category

#: Which fibre of the section a detail sits on.
FIBRE_TOP: Final[str] = "top"
FIBRE_BOTTOM: Final[str] = "bottom"
FIBRE_WEB: Final[str] = "web"
FIBRES: Final[tuple[str, ...]] = (FIBRE_TOP, FIBRE_BOTTOM, FIBRE_WEB)

#: Detail kinds this inventory records, and the category each usually carries.
#: The usual category is a starting point for an inspector, never a substitute
#: for reading the drawing.
KIND_DEFAULT_CATEGORY: Final[dict[str, str]] = {
    "base_metal": "A",
    "groove_weld": "B",
    "longitudinal_weld": "B'",
    "stiffener_weld": "C",
    "gusset": "D",
    "cover_plate_end": "E",
    "thick_cover_plate_end": "E'",
}


@dataclass(frozen=True, slots=True)
class FatigueDetail:
    """One fatigue sensitive location on one girder."""

    detail_id: str
    kind: str
    category_name: str
    station_ft: float
    fibre: str
    gauge_ids: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""

    def __post_init__(self) -> None:
        if not self.detail_id.strip():
            raise InputError("a fatigue detail needs an id")
        if self.kind not in KIND_DEFAULT_CATEGORY:
            raise InputError(f"{self.detail_id}: unknown detail kind {self.kind!r}")
        if self.fibre not in FIBRES:
            raise InputError(f"{self.detail_id}: unknown fibre {self.fibre!r}, expected {FIBRES}")
        if self.station_ft < 0.0:
            raise InputError(f"{self.detail_id}: station {self.station_ft} is behind the datum")
        if len(set(self.gauge_ids)) != len(self.gauge_ids):
            raise InputError(f"{self.detail_id}: the same gauge is listed twice")
        # A category name off a field sheet is an input problem, not a problem
        # with the category table, so the ConfigError is re translated here.
        try:
            category(self.category_name)
        except ConfigError as exc:
            raise InputError(f"{self.detail_id}: {exc}") from exc

    @property
    def detail_category(self) -> DetailCategory:
        """The category this detail is rated against."""
        return category(self.category_name)

    @property
    def is_instrumented(self) -> bool:
        """True when at least one gauge is watching this detail."""
        return bool(self.gauge_ids)

    @property
    def is_worse_than_its_kind_suggests(self) -> bool:
        """True when the recorded category is weaker than the kind's default.

        This is the flag an inspector wants: a stiffener weld recorded as an E
        prime means somebody found something on site, and the reason should be
        in the note.
        """
        usual = category(KIND_DEFAULT_CATEGORY[self.kind])
        return self.detail_category.constant_a < usual.constant_a

    def with_gauges(self, gauge_ids: Iterable[str]) -> FatigueDetail:
        """A copy watching a different set of gauges."""
        return FatigueDetail(
            detail_id=self.detail_id,
            kind=self.kind,
            category_name=self.category_name,
            station_ft=self.station_ft,
            fibre=self.fibre,
            gauge_ids=tuple(gauge_ids),
            note=self.note,
        )


def default_category(kind: str) -> str:
    """The category a detail kind usually carries."""
    if kind not in KIND_DEFAULT_CATEGORY:
        raise InputError(f"unknown detail kind {kind!r}")
    return KIND_DEFAULT_CATEGORY[kind]


def governing(details: Sequence[FatigueDetail]) -> FatigueDetail:
    """The weakest detail in a set, ties broken by station then id.

    Weakest means smallest detail constant. Two details of the same category at
    different stations see different stress ranges, so this is only the right
    answer for details that share a section; callers with a whole girder should
    rate each one.
    """
    if not details:
        raise InputError("no details to choose between")
    return min(
        details,
        key=lambda d: (d.detail_category.constant_a, d.station_ft, d.detail_id),
    )


def instrumented(details: Sequence[FatigueDetail]) -> list[FatigueDetail]:
    """Only the details a gauge is watching, in station order."""
    return sorted(
        (d for d in details if d.is_instrumented), key=lambda d: (d.station_ft, d.detail_id)
    )


def by_gauge(details: Sequence[FatigueDetail], gauge_id: str) -> list[FatigueDetail]:
    """Every detail one gauge is watching.

    A gauge on a flange near a stiffener watches both the stiffener weld and the
    flange base metal, so this returns a list rather than one detail.
    """
    return [d for d in details if gauge_id in d.gauge_ids]
