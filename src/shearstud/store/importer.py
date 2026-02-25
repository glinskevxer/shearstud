"""Reading a structure out of a JSON document, and writing one back.

The document is the exchange format between this package and the drawing office,
and it is the only place where a typing mistake in a plate dimension can enter
the inventory. So it is validated hard: every key is required unless a default
is written down here, an unknown key is an error rather than an ignore, and
every number goes through the same domain constructors the rest of the package
uses, which means a plate with no thickness is refused by the plate class rather
than by a check here that could drift away from it.

Refusing an unknown key is the part that gets argued about. A document with
``thicknes_in`` in it is a document somebody meant to say something with, and
accepting it silently means the plate keeps its default and the girder is wrong
by whatever the typo was worth.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shearstud.errors import InputError
from shearstud.geometry.composite import DeckSlab
from shearstud.geometry.effective import DeckLayout
from shearstud.geometry.plate import Plate
from shearstud.geometry.schedule import GirderSchedule, SectionRun
from shearstud.geometry.section import Section
from shearstud.structure.detail import FatigueDetail
from shearstud.structure.girder import GirderLine
from shearstud.structure.identity import parse
from shearstud.structure.record import Structure
from shearstud.structure.span import series

#: Keys a structure document may carry.
STRUCTURE_KEYS = frozenset(
    {"number", "name", "year_built", "spans", "continuous", "effective_width_rule", "girders"}
)

#: Keys a girder object may carry.
GIRDER_KEYS = frozenset(
    {
        "girder_id",
        "girder_index",
        "spacing_left_ft",
        "spacing_right_ft",
        "overhang_ft",
        "slab_thickness_in",
        "haunch_in",
        "deck_fc_ksi",
        "runs",
        "details",
    }
)

#: Keys a section run may carry.
RUN_KEYS = frozenset({"from_station_ft", "to_station_ft", "label", "plates"})

#: Keys a plate may carry.
PLATE_KEYS = frozenset({"label", "width_in", "height_in", "y_center_in"})

#: Keys a detail may carry.
DETAIL_KEYS = frozenset({"detail_id", "kind", "category_name", "station_ft", "fibre", "note"})


def _check_keys(entry: dict[str, Any], allowed: frozenset[str], what: str) -> None:
    unknown = sorted(set(entry) - allowed)
    if unknown:
        raise InputError(f"{what}: unknown key {unknown[0]!r}")


def _need(entry: dict[str, Any], key: str, what: str) -> Any:
    if key not in entry:
        raise InputError(f"{what}: missing {key!r}")
    return entry[key]


def _plate(entry: dict[str, Any], what: str) -> Plate:
    _check_keys(entry, PLATE_KEYS, what)
    return Plate(
        label=str(_need(entry, "label", what)),
        width_in=float(_need(entry, "width_in", what)),
        height_in=float(_need(entry, "height_in", what)),
        y_center_in=float(_need(entry, "y_center_in", what)),
    )


def _run(entry: dict[str, Any], index: int, girder_id: str) -> SectionRun:
    what = f"{girder_id} run {index}"
    _check_keys(entry, RUN_KEYS, what)
    plates = _need(entry, "plates", what)
    if not isinstance(plates, list) or not plates:
        raise InputError(f"{what}: needs at least one plate")
    return SectionRun(
        from_station_ft=float(_need(entry, "from_station_ft", what)),
        to_station_ft=float(_need(entry, "to_station_ft", what)),
        section=Section(
            label=str(entry.get("label", f"{girder_id}-{index}")),
            plates=tuple(_plate(p, f"{what} plate {i}") for i, p in enumerate(plates)),
        ),
    )


def _detail(entry: dict[str, Any], girder_id: str) -> FatigueDetail:
    what = f"{girder_id} detail"
    _check_keys(entry, DETAIL_KEYS, what)
    return FatigueDetail(
        detail_id=str(_need(entry, "detail_id", what)),
        kind=str(_need(entry, "kind", what)),
        category_name=str(_need(entry, "category_name", what)),
        station_ft=float(_need(entry, "station_ft", what)),
        fibre=str(_need(entry, "fibre", what)),
        note=str(entry.get("note", "")),
    )


def _girder(entry: dict[str, Any]) -> GirderLine:
    girder_id = str(_need(entry, "girder_id", "girder"))
    _check_keys(entry, GIRDER_KEYS, girder_id)
    runs = _need(entry, "runs", girder_id)
    if not isinstance(runs, list) or not runs:
        raise InputError(f"{girder_id}: needs at least one section run")
    layout = DeckLayout(
        girder_index=int(_need(entry, "girder_index", girder_id)),
        spacing_left_ft=float(entry.get("spacing_left_ft", 0.0)),
        spacing_right_ft=float(entry.get("spacing_right_ft", 0.0)),
        overhang_ft=float(entry.get("overhang_ft", 0.0)),
        slab_thickness_in=float(_need(entry, "slab_thickness_in", girder_id)),
    )
    tributary_in = (
        layout.spacing_left_ft / 2.0 + layout.spacing_right_ft / 2.0 + layout.overhang_ft
    ) * 12.0
    deck = DeckSlab(
        thickness_in=layout.slab_thickness_in,
        effective_width_in=tributary_in,
        haunch_in=float(entry.get("haunch_in", 0.0)),
        fc_ksi=float(entry.get("deck_fc_ksi", 4.0)),
    )
    details = [_detail(d, girder_id) for d in entry.get("details", [])]
    details.sort(key=lambda d: (d.station_ft, d.detail_id))
    return GirderLine(
        girder_id=girder_id,
        schedule=GirderSchedule(
            girder_id, tuple(_run(r, i, girder_id) for i, r in enumerate(runs))
        ),
        layout=layout,
        deck=deck,
        details=tuple(details),
    )


def from_document(document: dict[str, Any]) -> Structure:
    """Build a structure from a parsed JSON document."""
    _check_keys(document, STRUCTURE_KEYS, "structure")
    spans = _need(document, "spans", "structure")
    if not isinstance(spans, list) or not spans:
        raise InputError("structure: spans must be a list with at least one length")
    girders = _need(document, "girders", "structure")
    if not isinstance(girders, list) or not girders:
        raise InputError("structure: girders must be a list with at least one girder")
    return Structure(
        number=parse(str(_need(document, "number", "structure"))),
        name=str(_need(document, "name", "structure")),
        spans=series([float(v) for v in spans], continuous=bool(document.get("continuous", False))),
        girders=tuple(_girder(g) for g in girders),
        year_built=int(document.get("year_built", 0)),
        effective_width_rule=str(document.get("effective_width_rule", "tributary")),
    )


def read(path: Path | str) -> Structure:
    """Read a structure document off disk."""
    target = Path(path)
    if not target.exists():
        raise InputError(f"no structure document at {target}")
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InputError(f"{target.name} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise InputError(f"{target.name}: the document must be an object")
    return from_document(document)


def to_document(structure: Structure) -> dict[str, Any]:
    """Turn a structure back into a document, for a round trip."""
    return {
        "number": str(structure.number),
        "name": structure.name,
        "year_built": structure.year_built,
        "spans": list(structure.spans.lengths_ft),
        "continuous": structure.spans.continuous,
        "effective_width_rule": structure.effective_width_rule,
        "girders": [
            {
                "girder_id": g.girder_id,
                "girder_index": g.layout.girder_index,
                "spacing_left_ft": g.layout.spacing_left_ft,
                "spacing_right_ft": g.layout.spacing_right_ft,
                "overhang_ft": g.layout.overhang_ft,
                "slab_thickness_in": g.layout.slab_thickness_in,
                "haunch_in": g.deck.haunch_in,
                "deck_fc_ksi": g.deck.fc_ksi,
                "runs": [
                    {
                        "from_station_ft": run.from_station_ft,
                        "to_station_ft": run.to_station_ft,
                        "label": run.section.label,
                        "plates": [
                            {
                                "label": p.label,
                                "width_in": p.width_in,
                                "height_in": p.height_in,
                                "y_center_in": p.y_center_in,
                            }
                            for p in run.section
                        ],
                    }
                    for run in g.schedule
                ],
                "details": [
                    {
                        "detail_id": d.detail_id,
                        "kind": d.kind,
                        "category_name": d.category_name,
                        "station_ft": d.station_ft,
                        "fibre": d.fibre,
                        "note": d.note,
                    }
                    for d in g.details
                ],
            }
            for g in structure.girders
        ],
    }


def write(path: Path | str, structure: Structure) -> None:
    """Write a structure document to disk, formatted so a diff is readable."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(to_document(structure), indent=2, sort_keys=False)
    target.write_text(text + "\n", encoding="utf-8", newline="\n")
