"""The inventory: structures, girders and the details welded to them."""

from __future__ import annotations

from typing import Final

VERSION: Final[int] = 1
NAME: Final[str] = "structures"

UP: Final[str] = """
CREATE TABLE structures (
    number                TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    county_code           INTEGER NOT NULL,
    route_class           TEXT NOT NULL,
    sequence              INTEGER NOT NULL,
    parallel              TEXT NOT NULL DEFAULT '',
    year_built            INTEGER NOT NULL,
    span_lengths_ft       TEXT NOT NULL,
    continuous            INTEGER NOT NULL CHECK (continuous IN (0, 1)),
    effective_width_rule  TEXT NOT NULL,
    steel_grade           TEXT NOT NULL,
    member_condition      TEXT NOT NULL,
    redundancy            TEXT NOT NULL,
    adtt                  REAL NOT NULL CHECK (adtt >= 0),
    lanes_available       INTEGER NOT NULL CHECK (lanes_available >= 1),
    growth_pct_per_yr     REAL NOT NULL
);

CREATE TABLE girders (
    structure_number   TEXT NOT NULL REFERENCES structures(number) ON DELETE CASCADE,
    girder_id          TEXT NOT NULL,
    girder_index       INTEGER NOT NULL CHECK (girder_index >= 0),
    spacing_left_ft    REAL NOT NULL CHECK (spacing_left_ft >= 0),
    spacing_right_ft   REAL NOT NULL CHECK (spacing_right_ft >= 0),
    overhang_ft        REAL NOT NULL CHECK (overhang_ft >= 0),
    slab_thickness_in  REAL NOT NULL CHECK (slab_thickness_in > 0),
    haunch_in          REAL NOT NULL CHECK (haunch_in >= 0),
    deck_fc_ksi        REAL NOT NULL CHECK (deck_fc_ksi > 0),
    PRIMARY KEY (structure_number, girder_id)
);

CREATE UNIQUE INDEX girders_by_index
    ON girders (structure_number, girder_index);

CREATE TABLE section_runs (
    structure_number  TEXT NOT NULL,
    girder_id         TEXT NOT NULL,
    run_index         INTEGER NOT NULL CHECK (run_index >= 0),
    from_station_ft   REAL NOT NULL CHECK (from_station_ft >= 0),
    to_station_ft     REAL NOT NULL,
    section_label     TEXT NOT NULL,
    PRIMARY KEY (structure_number, girder_id, run_index),
    FOREIGN KEY (structure_number, girder_id)
        REFERENCES girders(structure_number, girder_id) ON DELETE CASCADE,
    CHECK (to_station_ft > from_station_ft)
);

CREATE TABLE section_plates (
    structure_number  TEXT NOT NULL,
    girder_id         TEXT NOT NULL,
    run_index         INTEGER NOT NULL,
    plate_label       TEXT NOT NULL,
    width_in          REAL NOT NULL CHECK (width_in > 0),
    height_in         REAL NOT NULL CHECK (height_in > 0),
    y_center_in       REAL NOT NULL,
    PRIMARY KEY (structure_number, girder_id, run_index, plate_label),
    FOREIGN KEY (structure_number, girder_id, run_index)
        REFERENCES section_runs(structure_number, girder_id, run_index) ON DELETE CASCADE
);

CREATE TABLE details (
    detail_id         TEXT PRIMARY KEY,
    structure_number  TEXT NOT NULL,
    girder_id         TEXT NOT NULL,
    kind              TEXT NOT NULL,
    category_name     TEXT NOT NULL,
    station_ft        REAL NOT NULL CHECK (station_ft >= 0),
    fibre             TEXT NOT NULL CHECK (fibre IN ('top', 'bottom', 'web')),
    note              TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (structure_number, girder_id)
        REFERENCES girders(structure_number, girder_id) ON DELETE CASCADE
);

CREATE INDEX details_by_girder
    ON details (structure_number, girder_id, station_ft);
"""
