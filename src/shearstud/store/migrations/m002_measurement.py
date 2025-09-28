"""What is measured: gauges, campaigns, cycle spectra and thickness readings."""

from __future__ import annotations

from typing import Final

VERSION: Final[int] = 2
NAME: Final[str] = "measurement"

UP: Final[str] = """
CREATE TABLE gauges (
    gauge_id          TEXT PRIMARY KEY,
    detail_id         TEXT NOT NULL REFERENCES details(detail_id) ON DELETE CASCADE,
    orientation       TEXT NOT NULL
        CHECK (orientation IN ('longitudinal', 'transverse', 'diagonal')),
    gauge_factor      REAL NOT NULL CHECK (gauge_factor > 0),
    installed_on      TEXT NOT NULL,
    removed_on        TEXT,
    channel_limit_ue  REAL NOT NULL CHECK (channel_limit_ue > 0),
    CHECK (removed_on IS NULL OR removed_on >= installed_on)
);

CREATE INDEX gauges_by_detail ON gauges (detail_id);

CREATE TABLE campaigns (
    campaign_id       TEXT PRIMARY KEY,
    structure_number  TEXT NOT NULL REFERENCES structures(number) ON DELETE CASCADE,
    started_on        TEXT NOT NULL,
    ended_on          TEXT NOT NULL,
    seasonal_factor   REAL NOT NULL DEFAULT 1.0 CHECK (seasonal_factor > 0),
    note              TEXT NOT NULL DEFAULT '',
    CHECK (ended_on >= started_on)
);

CREATE INDEX campaigns_by_structure ON campaigns (structure_number, started_on);

CREATE TABLE spectra (
    campaign_id    TEXT NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
    gauge_id       TEXT NOT NULL REFERENCES gauges(gauge_id) ON DELETE CASCADE,
    bin_width_ue   REAL NOT NULL CHECK (bin_width_ue > 0),
    dropout_frac   REAL NOT NULL DEFAULT 0.0 CHECK (dropout_frac BETWEEN 0 AND 1),
    railed_frac    REAL NOT NULL DEFAULT 0.0 CHECK (railed_frac BETWEEN 0 AND 1),
    PRIMARY KEY (campaign_id, gauge_id)
);

CREATE TABLE spectrum_bins (
    campaign_id       TEXT NOT NULL,
    gauge_id          TEXT NOT NULL,
    low_ue            REAL NOT NULL CHECK (low_ue >= 0),
    count             REAL NOT NULL CHECK (count >= 0),
    representative_ue REAL NOT NULL CHECK (representative_ue >= 0),
    PRIMARY KEY (campaign_id, gauge_id, low_ue),
    FOREIGN KEY (campaign_id, gauge_id)
        REFERENCES spectra(campaign_id, gauge_id) ON DELETE CASCADE
);

CREATE TABLE thickness_readings (
    reading_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    structure_number  TEXT NOT NULL,
    girder_id         TEXT NOT NULL,
    plate_label       TEXT NOT NULL,
    station_ft        REAL NOT NULL CHECK (station_ft >= 0),
    remaining_in      REAL NOT NULL CHECK (remaining_in > 0),
    measured_on       TEXT NOT NULL,
    FOREIGN KEY (structure_number, girder_id)
        REFERENCES girders(structure_number, girder_id) ON DELETE CASCADE
);

CREATE INDEX readings_by_girder
    ON thickness_readings (structure_number, girder_id, measured_on);
"""
