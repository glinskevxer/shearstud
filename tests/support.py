"""One structure document, built five different ways in five test files.

Every command line test needed a structure in the book, so every command line
test grew its own JSON builder. They drifted: one had four girders and no
details, one had two girders and two details, one wrote plates as a helper call
and one as literals, and one quietly omitted the deck strength. When the
importer gained a required field, four of the five needed the same edit and the
fifth was found by the type checker rather than by a test.

So there is one builder here and it takes arguments for the things the tests
actually varied. What a test needs that this cannot express, it should build
itself and say why in a comment, because the next person will otherwise add a
sixth parameter nobody else uses.

This is a plain module rather than fixtures in ``conftest.py`` because most of
it is called with arguments, and a fixture that takes arguments has to be a
factory fixture, which is two layers of indirection to save an import.
"""

from __future__ import annotations

from typing import Any

#: The structure every command line test works against.
NUMBER = "18-SH-0473"
NAME = "Salt Fork Creek"

#: The span, and the plates of the section that carries it.
SPAN_FT = 90.0
WEB_DEPTH_IN = 52.0
TOP_FLANGE_IN = 1.0


def plate(label: str, width_in: float, height_in: float, y_center_in: float) -> dict[str, Any]:
    """One plate of a section, as the import document writes it."""
    return {
        "label": label,
        "width_in": width_in,
        "height_in": height_in,
        "y_center_in": y_center_in,
    }


def plates(bottom_in: float = 1.5) -> list[dict[str, Any]]:
    """A plate girder section: heavy bottom flange, lighter top one."""
    return [
        plate("bottom", 18.0, bottom_in, bottom_in / 2.0),
        plate("web", 0.5625, WEB_DEPTH_IN, bottom_in + WEB_DEPTH_IN / 2.0),
        plate("top", 16.0, TOP_FLANGE_IN, bottom_in + WEB_DEPTH_IN + TOP_FLANGE_IN / 2.0),
    ]


def cover_plate_end(detail_id: str = "D1", station_ft: float = 24.0) -> dict[str, Any]:
    """The worst fatigue detail on the older stringers in this inventory."""
    return {
        "detail_id": detail_id,
        "kind": "cover_plate_end",
        "category_name": "E",
        "station_ft": station_ft,
        "fibre": "bottom",
    }


def stiffener_weld(detail_id: str = "D2", station_ft: float = 45.0) -> dict[str, Any]:
    """A transverse stiffener weld on the web, which is a milder category."""
    return {
        "detail_id": detail_id,
        "kind": "stiffener_weld",
        "category_name": "C",
        "station_ft": station_ft,
        "fibre": "web",
    }


def girder(
    index: int,
    girder_count: int,
    *,
    bottom_in: float = 1.5,
    span_ft: float = SPAN_FT,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One girder line, exterior when it is first or last.

    A cross section of one girder is not a bridge and the structure model
    refuses it, so a lone girder keeps a neighbour on its right. The tests that
    ask for one are testing something else and want the smallest structure that
    will load.
    """
    exterior = index in (0, girder_count - 1)
    alone = girder_count == 1
    return {
        "girder_id": f"G{index + 1}",
        "girder_index": index,
        "spacing_left_ft": 0.0 if index == 0 else 8.0,
        "spacing_right_ft": 0.0 if index == girder_count - 1 and not alone else 8.0,
        "overhang_ft": 3.5 if exterior else 0.0,
        "slab_thickness_in": 8.0,
        "haunch_in": 2.0,
        "deck_fc_ksi": 4.0,
        "runs": [
            {
                "from_station_ft": 0.0,
                "to_station_ft": span_ft,
                "label": "PG52",
                "plates": plates(bottom_in),
            }
        ],
        "details": details if details is not None else [],
    }


def document(
    number: str = NUMBER,
    *,
    girder_count: int = 4,
    bottom_in: float = 1.5,
    span_ft: float = SPAN_FT,
    details_on_first: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A whole structure as the importer reads it.

    ``details_on_first`` puts fatigue details on G1 and leaves the rest bare,
    which is the shape the measurement tests want: one instrumented girder and
    three that nobody has looked at.
    """
    girders = [
        girder(
            index,
            girder_count,
            bottom_in=bottom_in,
            span_ft=span_ft,
            details=details_on_first if index == 0 else [],
        )
        for index in range(girder_count)
    ]
    return {
        "number": number,
        "name": NAME,
        "year_built": 1968,
        "spans": [span_ft],
        "continuous": False,
        "effective_width_rule": "tributary",
        "girders": girders,
    }


#: The columns a raw structure insert has to fill, and the values that go with
#: them. Six test files were writing this statement out by hand.
STRUCTURE_COLUMNS = (
    "number, name, county_code, route_class, sequence, parallel, year_built, "
    "span_lengths_ft, continuous, effective_width_rule, steel_grade, "
    "member_condition, redundancy, adtt, lanes_available, growth_pct_per_yr"
)

STRUCTURE_PLACEHOLDERS = ", ".join("?" * 16)


def structure_row(
    number: str = NUMBER,
    *,
    name: str = NAME,
    county_code: int = 18,
    route_class: str = "SH",
    sequence: int = 473,
    redundancy: str = "redundant",
    year_built: int = 1968,
    span_lengths_ft: str = "[90.0]",
    effective_width_rule: str = "tributary",
    steel_grade: str = "A36",
    member_condition: str = "good",
    adtt: float = 1200.0,
    growth_pct_per_yr: float = 2.0,
) -> tuple[Any, ...]:
    """The values for a raw structure insert, in column order.

    Every argument is one a test has actually varied. The order matters and is
    the only thing about this that is worth getting wrong once: sixteen
    positional values against sixteen column names is exactly the shape of
    mistake a named helper exists to stop.
    """
    return (
        number,
        name,
        county_code,
        route_class,
        sequence,
        "",
        year_built,
        span_lengths_ft,
        0,
        effective_width_rule,
        steel_grade,
        member_condition,
        redundancy,
        adtt,
        2,
        growth_pct_per_yr,
    )


def insert_structure_sql() -> str:
    """The insert a test uses to put a structure in without the repository.

    Raw SQL on purpose. A store test that seeded itself through the repository
    could pass because the seeding and the code under test share a bug.
    """
    return f"INSERT INTO structures ({STRUCTURE_COLUMNS}) VALUES ({STRUCTURE_PLACEHOLDERS})"
