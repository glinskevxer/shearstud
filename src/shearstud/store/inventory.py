"""Reading and writing whole structures.

The unit of work is the structure, not the row. A girder without its structure
is not a thing this package can do anything with, and a structure loaded without
its section plates cannot be rated, so the repository loads and saves the whole
aggregate and there is no way to ask it for half of one.

Saving replaces. A structure that is already in the book is deleted and written
again inside one transaction, which is what makes a partial write impossible and
what makes the foreign key cascades on the schema load bearing rather than
decorative. The cost is that a save has to carry everything, and that is the
point: a save that carried only what changed would let a girder quietly keep a
detail the caller had removed.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from shearstud.errors import StorageError
from shearstud.geometry.composite import DeckSlab
from shearstud.geometry.effective import DeckLayout
from shearstud.geometry.plate import Plate
from shearstud.geometry.schedule import GirderSchedule, SectionRun
from shearstud.geometry.section import Section
from shearstud.store import db
from shearstud.structure.detail import FatigueDetail
from shearstud.structure.girder import GirderLine
from shearstud.structure.identity import parse
from shearstud.structure.record import Structure
from shearstud.structure.span import SpanArrangement, series

#: How the load finds another way round when a member goes.
#:
#: ``nonredundant`` is what the regulation calls a non redundant steel tension
#: member and what the office still calls fracture critical. ``limited`` is a
#: two girder unit or a two line truss that has some internal redundancy but
#: not enough to be relied on, and this inventory has eleven of them. It exists
#: as its own word rather than being filed under one of the other two because
#: an inspector needs to be able to write down what they found; every rule that
#: acts on it treats it as non redundant.
REDUNDANT = "redundant"
LIMITED = "limited"
NONREDUNDANT = "nonredundant"
REDUNDANCIES = (REDUNDANT, LIMITED, NONREDUNDANT)

#: The redundancies that get the treatment a non redundant structure gets.
NOT_RELIED_ON = (LIMITED, NONREDUNDANT)

#: Fields the structures table carries beyond the identity.
_STRUCTURE_COLUMNS = (
    "number, name, county_code, route_class, sequence, parallel, year_built, "
    "span_lengths_ft, continuous, effective_width_rule, steel_grade, "
    "member_condition, redundancy, adtt, lanes_available, growth_pct_per_yr"
)


@dataclass(frozen=True, slots=True)
class StructurePolicy:
    """The fields a structure carries that are agency judgement, not geometry.

    They live beside the structure rather than inside it because they change on
    a different clock: a girder's plates are fixed for the life of the bridge
    and its condition rating changes every two years.
    """

    steel_grade: str = "A36"
    member_condition: str = "good"
    redundancy: str = REDUNDANT
    adtt: float = 0.0
    lanes_available: int = 2
    growth_pct_per_yr: float = 0.0

    def __post_init__(self) -> None:
        if self.redundancy not in REDUNDANCIES:
            raise StorageError(
                f"unknown redundancy {self.redundancy!r}, expected one of {REDUNDANCIES}"
            )
        if self.adtt < 0.0:
            raise StorageError(f"truck traffic {self.adtt} is negative")
        if self.lanes_available < 1:
            raise StorageError(f"{self.lanes_available} lanes is not a roadway")

    @property
    def is_nonredundant(self) -> bool:
        """True when the structure gets the non redundant treatment.

        Limited redundancy answers true here. A rule that acts on this is
        deciding how often somebody climbs the structure, and there is no
        version of that decision where "some redundancy, not enough to rely
        on" should buy a longer interval.
        """
        return self.redundancy in NOT_RELIED_ON


def save(path: Path | str, structure: Structure, policy: StructurePolicy | None = None) -> None:
    """Write a structure, replacing whatever was there under that number."""
    settings = policy or StructurePolicy()
    number = str(structure.number)
    with db.transaction(path) as connection:
        connection.execute("DELETE FROM structures WHERE number = ?", (number,))
        connection.execute(
            f"INSERT INTO structures ({_STRUCTURE_COLUMNS}) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                number,
                structure.name,
                structure.number.county_code,
                structure.number.route_class,
                structure.number.sequence,
                structure.number.parallel,
                structure.year_built,
                json.dumps(list(structure.spans.lengths_ft)),
                int(structure.spans.continuous),
                structure.effective_width_rule,
                settings.steel_grade,
                settings.member_condition,
                settings.redundancy,
                settings.adtt,
                settings.lanes_available,
                settings.growth_pct_per_yr,
            ),
        )
        for girder in structure.girders:
            _save_girder(connection, number, girder)


def _save_girder(connection: sqlite3.Connection, number: str, girder: GirderLine) -> None:
    execute = connection.execute
    execute(
        "INSERT INTO girders (structure_number, girder_id, girder_index, "
        "spacing_left_ft, spacing_right_ft, overhang_ft, slab_thickness_in, "
        "haunch_in, deck_fc_ksi) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            number,
            girder.girder_id,
            girder.layout.girder_index,
            girder.layout.spacing_left_ft,
            girder.layout.spacing_right_ft,
            girder.layout.overhang_ft,
            girder.layout.slab_thickness_in,
            girder.deck.haunch_in,
            girder.deck.fc_ksi,
        ),
    )
    for run_index, run in enumerate(girder.schedule):
        execute(
            "INSERT INTO section_runs (structure_number, girder_id, run_index, "
            "from_station_ft, to_station_ft, section_label) VALUES (?, ?, ?, ?, ?, ?)",
            (
                number,
                girder.girder_id,
                run_index,
                run.from_station_ft,
                run.to_station_ft,
                run.section.label,
            ),
        )
        for plate in run.section:
            execute(
                "INSERT INTO section_plates (structure_number, girder_id, run_index, "
                "plate_label, width_in, height_in, y_center_in) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    number,
                    girder.girder_id,
                    run_index,
                    plate.label,
                    plate.width_in,
                    plate.height_in,
                    plate.y_center_in,
                ),
            )
    for detail in girder.details:
        execute(
            "INSERT INTO details (detail_id, structure_number, girder_id, kind, "
            "category_name, station_ft, fibre, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                detail.detail_id,
                number,
                girder.girder_id,
                detail.kind,
                detail.category_name,
                detail.station_ft,
                detail.fibre,
                detail.note,
            ),
        )


def load(path: Path | str, number: str) -> Structure:
    """Read one structure back, whole."""
    row = db.fetch_one(
        path, f"SELECT {_STRUCTURE_COLUMNS} FROM structures WHERE number = ?", (number,)
    )
    if row is None:
        raise StorageError(f"no structure {number!r} in the book of record")
    spans = _load_spans(str(row["span_lengths_ft"]), continuous=bool(row["continuous"]))
    girders = tuple(_load_girders(path, number))
    return Structure(
        number=parse(str(row["number"])),
        name=str(row["name"]),
        spans=spans,
        girders=girders,
        year_built=int(row["year_built"]),
        effective_width_rule=str(row["effective_width_rule"]),
    )


@dataclass(frozen=True, slots=True)
class StructureSummary:
    """A structure as a listing or a report needs it, without the geometry.

    Loading a whole structure means every plate of every section run, and a
    listing of four hundred structures does not need one of them. This is four
    counting queries and it is what the reports read.
    """

    number: str
    name: str
    year_built: int
    spans: SpanArrangement
    girder_count: int
    detail_count: int
    gauge_count: int

    @property
    def length_ft(self) -> float:
        """End to end length of the unit."""
        return self.spans.total_length_ft

    @property
    def is_instrumented(self) -> bool:
        """True when at least one gauge is on the structure."""
        return self.gauge_count > 0


def summary(path: Path | str, number: str) -> StructureSummary:
    """What a listing or a report needs about one structure."""
    row = db.fetch_one(
        path,
        "SELECT number, name, year_built, span_lengths_ft, continuous "
        "FROM structures WHERE number = ?",
        (number,),
    )
    if row is None:
        raise StorageError(f"no structure {number!r} in the book of record")
    counts = db.fetch_one(
        path,
        "SELECT "
        "(SELECT COUNT(*) FROM girders WHERE structure_number = ?) AS girders, "
        "(SELECT COUNT(*) FROM details WHERE structure_number = ?) AS details, "
        "(SELECT COUNT(*) FROM gauges g JOIN details d ON d.detail_id = g.detail_id "
        " WHERE d.structure_number = ?) AS gauges",
        (number, number, number),
    )
    if counts is None:  # pragma: no cover - a scalar subquery always returns a row
        raise StorageError(f"could not count what hangs off {number!r}")
    return StructureSummary(
        number=str(row["number"]),
        name=str(row["name"]),
        year_built=int(row["year_built"]),
        spans=_load_spans(str(row["span_lengths_ft"]), continuous=bool(row["continuous"])),
        girder_count=int(counts["girders"]),
        detail_count=int(counts["details"]),
        gauge_count=int(counts["gauges"]),
    )


def summaries(path: Path | str) -> list[StructureSummary]:
    """Every structure in the book, in file cabinet order."""
    return [summary(path, number) for number in numbers(path)]


def _load_spans(lengths_json: str, *, continuous: bool) -> SpanArrangement:
    lengths = [float(v) for v in json.loads(lengths_json)]
    return series(lengths, continuous=continuous)


def _load_girders(path: Path | str, number: str) -> list[GirderLine]:
    rows = db.fetch_all(
        path,
        "SELECT girder_id, girder_index, spacing_left_ft, spacing_right_ft, "
        "overhang_ft, slab_thickness_in, haunch_in, deck_fc_ksi FROM girders "
        "WHERE structure_number = ? ORDER BY girder_index",
        (number,),
    )
    out: list[GirderLine] = []
    for row in rows:
        girder_id = str(row["girder_id"])
        layout = DeckLayout(
            girder_index=int(row["girder_index"]),
            spacing_left_ft=float(row["spacing_left_ft"]),
            spacing_right_ft=float(row["spacing_right_ft"]),
            overhang_ft=float(row["overhang_ft"]),
            slab_thickness_in=float(row["slab_thickness_in"]),
        )
        deck = DeckSlab(
            thickness_in=float(row["slab_thickness_in"]),
            effective_width_in=(
                float(row["spacing_left_ft"]) / 2.0
                + float(row["spacing_right_ft"]) / 2.0
                + float(row["overhang_ft"])
            )
            * 12.0,
            haunch_in=float(row["haunch_in"]),
            fc_ksi=float(row["deck_fc_ksi"]),
        )
        out.append(
            GirderLine(
                girder_id=girder_id,
                schedule=_load_schedule(path, number, girder_id),
                layout=layout,
                deck=deck,
                details=tuple(_load_details(path, number, girder_id)),
            )
        )
    return out


def _load_schedule(path: Path | str, number: str, girder_id: str) -> GirderSchedule:
    rows = db.fetch_all(
        path,
        "SELECT run_index, from_station_ft, to_station_ft, section_label "
        "FROM section_runs WHERE structure_number = ? AND girder_id = ? "
        "ORDER BY run_index",
        (number, girder_id),
    )
    if not rows:
        raise StorageError(f"girder {girder_id!r} of {number} has no section runs")
    runs = []
    for row in rows:
        plates = _load_plates(path, number, girder_id, int(row["run_index"]))
        runs.append(
            SectionRun(
                from_station_ft=float(row["from_station_ft"]),
                to_station_ft=float(row["to_station_ft"]),
                section=Section(str(row["section_label"]), tuple(plates)),
            )
        )
    return GirderSchedule(girder_id, tuple(runs))


def _load_plates(path: Path | str, number: str, girder_id: str, run_index: int) -> list[Plate]:
    rows = db.fetch_all(
        path,
        "SELECT plate_label, width_in, height_in, y_center_in FROM section_plates "
        "WHERE structure_number = ? AND girder_id = ? AND run_index = ? "
        "ORDER BY y_center_in",
        (number, girder_id, run_index),
    )
    return [
        Plate(
            label=str(row["plate_label"]),
            width_in=float(row["width_in"]),
            height_in=float(row["height_in"]),
            y_center_in=float(row["y_center_in"]),
        )
        for row in rows
    ]


def _load_details(path: Path | str, number: str, girder_id: str) -> list[FatigueDetail]:
    rows = db.fetch_all(
        path,
        "SELECT detail_id, kind, category_name, station_ft, fibre, note FROM details "
        "WHERE structure_number = ? AND girder_id = ? ORDER BY station_ft, detail_id",
        (number, girder_id),
    )
    return [
        FatigueDetail(
            detail_id=str(row["detail_id"]),
            kind=str(row["kind"]),
            category_name=str(row["category_name"]),
            station_ft=float(row["station_ft"]),
            fibre=str(row["fibre"]),
            note=str(row["note"]),
        )
        for row in rows
    ]


def load_policy(path: Path | str, number: str) -> StructurePolicy:
    """The policy fields for one structure.

    Separate from :func:`load` because the callers are different: a rating needs
    the policy and the geometry, a listing needs the geometry alone, and the
    geometry is the expensive half.
    """
    row = db.fetch_one(
        path,
        "SELECT steel_grade, member_condition, redundancy, adtt, lanes_available, "
        "growth_pct_per_yr, continuous FROM structures WHERE number = ?",
        (number,),
    )
    if row is None:
        raise StorageError(f"no structure {number!r} in the book of record")
    return StructurePolicy(
        steel_grade=str(row["steel_grade"]),
        member_condition=str(row["member_condition"]),
        redundancy=str(row["redundancy"]),
        adtt=float(row["adtt"]),
        lanes_available=int(row["lanes_available"]),
        growth_pct_per_yr=float(row["growth_pct_per_yr"]),
    )


def is_continuous(path: Path | str, number: str) -> bool:
    """Whether a structure's spans are joined over its piers."""
    row = db.fetch_one(path, "SELECT continuous FROM structures WHERE number = ?", (number,))
    if row is None:
        raise StorageError(f"no structure {number!r} in the book of record")
    return bool(row["continuous"])


def numbers(path: Path | str) -> list[str]:
    """Every structure number in the book, in file cabinet order."""
    rows = db.fetch_all(
        path, "SELECT number FROM structures ORDER BY county_code, route_class, sequence, parallel"
    )
    return [str(row["number"]) for row in rows]


def exists(path: Path | str, number: str) -> bool:
    """Whether a structure is in the book."""
    return db.fetch_one(path, "SELECT 1 FROM structures WHERE number = ?", (number,)) is not None


def delete(path: Path | str, number: str) -> None:
    """Remove a structure and everything hanging off it."""
    touched = db.execute(path, "DELETE FROM structures WHERE number = ?", (number,))
    if touched == 0:
        raise StorageError(f"no structure {number!r} to delete")
