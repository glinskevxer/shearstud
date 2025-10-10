"""Fixtures shared across the suite.

The girders here are the ones the rest of the tests reason about, so they are
built once and described in one place. They are deliberately not the same
girder: a symmetric welded section, a singly symmetric one with a heavier
bottom flange, and a rolled stringer each fail differently.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from shearstud.geometry import rolled
from shearstud.geometry.composite import CompositeGirder, DeckSlab
from shearstud.geometry.plate import flange, web
from shearstud.geometry.section import Section
from shearstud.store import db, migrate


@pytest.fixture
def symmetric_plate_girder() -> Section:
    """54 inch web, 14 by 1 flanges, doubly symmetric."""
    return Section(
        "PG54",
        (
            flange("bottom", width_in=14.0, thickness_in=1.0, y_center_in=0.5),
            web("web", thickness_in=0.5, depth_in=54.0, y_center_in=28.0),
            flange("top", width_in=14.0, thickness_in=1.0, y_center_in=55.5),
        ),
    )


@pytest.fixture
def positive_moment_girder() -> Section:
    """The section a positive moment region actually carries: heavy bottom
    flange, light top flange because the deck helps in compression."""
    return Section(
        "PG54p",
        (
            flange("bottom", width_in=18.0, thickness_in=1.5, y_center_in=0.75),
            web("web", thickness_in=0.5, depth_in=54.0, y_center_in=28.5),
            flange("top", width_in=14.0, thickness_in=1.0, y_center_in=56.0),
        ),
    )


@pytest.fixture
def stringer() -> Section:
    """A rolled beam from the catalogue, for the older spans."""
    return rolled.shape("W30X116").section()


@pytest.fixture
def deck() -> DeckSlab:
    """An eight inch deck on a seven and a half foot girder spacing."""
    return DeckSlab(thickness_in=8.0, effective_width_in=90.0, haunch_in=2.0, fc_ksi=4.0)


@pytest.fixture
def composite_girder(positive_moment_girder: Section, deck: DeckSlab) -> CompositeGirder:
    """The girder every composite test works from."""
    return CompositeGirder(steel=positive_moment_girder, deck=deck)


@pytest.fixture(scope="session")
def migrated_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A book with every migration applied, built once for the whole run.

    Applying three migrations takes a few hundred milliseconds and the store
    tests want a fresh book each. Copying a template file is two orders of
    magnitude cheaper and gives exactly the same starting state.
    """
    path = tmp_path_factory.mktemp("template") / "template.sqlite3"
    migrate.upgrade(path)
    return path


@pytest.fixture
def book(tmp_path: Path, migrated_template: Path) -> Path:
    """An empty book at the newest schema."""
    path = tmp_path / "shearstud.sqlite3"
    shutil.copyfile(migrated_template, path)
    return path


#: The structure every store test that needs one works against.
SEED_NUMBER = "18-SH-0473"

#: The detail and campaign that hang off it.
SEED_DETAIL = "D07"
SEED_CAMPAIGN = "C-2025-04"


@pytest.fixture
def seeded_book(book: Path) -> Path:
    """A book holding one structure, one girder, one detail and one campaign.

    The rows are written with raw SQL rather than through the repository so
    that a repository test cannot pass because the seeding and the code under
    test share a bug.
    """
    with db.transaction(book) as connection:
        connection.execute(
            "INSERT INTO structures (number, name, county_code, route_class, sequence, "
            "parallel, year_built, span_lengths_ft, continuous, effective_width_rule, "
            "steel_grade, member_condition, redundancy, adtt, lanes_available, "
            "growth_pct_per_yr) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                SEED_NUMBER,
                "Salt Fork Creek",
                18,
                "SH",
                473,
                "",
                1968,
                "[120.0]",
                0,
                "tributary",
                "A36",
                "good",
                "redundant",
                1200.0,
                2,
                2.0,
            ),
        )
        connection.execute(
            "INSERT INTO girders (structure_number, girder_id, girder_index, "
            "spacing_left_ft, spacing_right_ft, overhang_ft, slab_thickness_in, "
            "haunch_in, deck_fc_ksi) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (SEED_NUMBER, "G3", 0, 7.5, 7.5, 0.0, 8.0, 2.0, 4.0),
        )
        connection.execute(
            "INSERT INTO details (detail_id, structure_number, girder_id, kind, "
            "category_name, station_ft, fibre) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (SEED_DETAIL, SEED_NUMBER, "G3", "cover_plate_end", "E", 24.5, "bottom"),
        )
        connection.execute(
            "INSERT INTO campaigns (campaign_id, structure_number, started_on, ended_on) "
            "VALUES (?, ?, ?, ?)",
            (SEED_CAMPAIGN, SEED_NUMBER, "2025-04-01", "2025-04-14"),
        )
    return book
