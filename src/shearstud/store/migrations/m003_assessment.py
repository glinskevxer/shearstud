"""What is concluded: ratings, fatigue evaluations and posting decisions."""

from __future__ import annotations

from typing import Final

VERSION: Final[int] = 3
NAME: Final[str] = "assessment"

UP: Final[str] = """
CREATE TABLE ratings (
    rating_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    structure_number  TEXT NOT NULL REFERENCES structures(number) ON DELETE CASCADE,
    girder_id         TEXT NOT NULL,
    station_ft        REAL NOT NULL CHECK (station_ft >= 0),
    limit_state       TEXT NOT NULL CHECK (limit_state IN ('strength_i', 'service_ii')),
    level             TEXT NOT NULL CHECK (level IN ('inventory', 'operating')),
    vehicle           TEXT NOT NULL,
    effect            TEXT NOT NULL CHECK (effect IN ('moment', 'shear')),
    capacity          REAL NOT NULL,
    factored_dead     REAL NOT NULL,
    factored_live     REAL NOT NULL,
    rating_factor     REAL NOT NULL,
    gross_weight_kip  REAL NOT NULL CHECK (gross_weight_kip > 0),
    rated_on          TEXT NOT NULL
);

CREATE INDEX ratings_by_structure
    ON ratings (structure_number, rated_on DESC);

CREATE UNIQUE INDEX ratings_unique_run
    ON ratings (structure_number, girder_id, station_ft, limit_state,
                level, vehicle, effect, rated_on);

CREATE TABLE evaluations (
    evaluation_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    detail_id              TEXT NOT NULL REFERENCES details(detail_id) ON DELETE CASCADE,
    campaign_id            TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    detail_category        TEXT NOT NULL,
    annual_cycles          REAL NOT NULL CHECK (annual_cycles >= 0),
    effective_range_ksi    REAL NOT NULL CHECK (effective_range_ksi >= 0),
    largest_range_ksi      REAL NOT NULL CHECK (largest_range_ksi >= 0),
    infinite_life          INTEGER NOT NULL CHECK (infinite_life IN (0, 1)),
    damage_per_first_year  REAL NOT NULL CHECK (damage_per_first_year >= 0),
    years_remaining        REAL NOT NULL,
    evaluated_on           TEXT NOT NULL
);

CREATE UNIQUE INDEX evaluations_unique_run
    ON evaluations (detail_id, campaign_id, evaluated_on);

CREATE INDEX evaluations_by_life
    ON evaluations (years_remaining);

CREATE TABLE postings (
    posting_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    structure_number  TEXT NOT NULL REFERENCES structures(number) ON DELETE CASCADE,
    outcome           TEXT NOT NULL CHECK (outcome IN ('open', 'posted', 'closed')),
    governing_factor  REAL NOT NULL,
    decided_on        TEXT NOT NULL,
    UNIQUE (structure_number, decided_on)
);

CREATE TABLE posting_lines (
    posting_id     INTEGER NOT NULL REFERENCES postings(posting_id) ON DELETE CASCADE,
    silhouette     TEXT NOT NULL,
    vehicle        TEXT NOT NULL,
    rating_factor  REAL NOT NULL,
    tons           REAL,
    PRIMARY KEY (posting_id, silhouette)
);
"""
