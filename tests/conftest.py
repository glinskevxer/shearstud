"""Fixtures shared across the suite.

The girders here are the ones the rest of the tests reason about, so they are
built once and described in one place. They are deliberately not the same
girder: a symmetric welded section, a singly symmetric one with a heavier
bottom flange, and a rolled stringer each fail differently.
"""

from __future__ import annotations

import pytest

from shearstud.geometry import rolled
from shearstud.geometry.composite import CompositeGirder, DeckSlab
from shearstud.geometry.plate import flange, web
from shearstud.geometry.section import Section


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
