"""Plate arithmetic, including the two ways a plate can be rejected."""

from __future__ import annotations

import pytest

from shearstud.errors import GeometryError
from shearstud.geometry.plate import Plate, flange, web

pytestmark = pytest.mark.geometry


def test_area_is_the_rectangle() -> None:
    p = Plate("bf", width_in=14.0, height_in=0.75, y_center_in=0.375)
    assert p.area_in2 == pytest.approx(10.5)


def test_own_inertia_is_bd_cubed_over_twelve() -> None:
    p = Plate("bf", width_in=12.0, height_in=2.0, y_center_in=0.0)
    assert p.inertia_own_in4 == pytest.approx(12.0 * 8.0 / 12.0)


def test_own_inertia_is_dominated_by_the_tall_dimension() -> None:
    tall = Plate("w", width_in=1.0, height_in=10.0, y_center_in=0.0)
    wide = Plate("f", width_in=10.0, height_in=1.0, y_center_in=0.0)
    assert tall.area_in2 == wide.area_in2
    assert tall.inertia_own_in4 == pytest.approx(100.0 * wide.inertia_own_in4)


def test_extreme_fibres_straddle_the_centre() -> None:
    p = Plate("w", width_in=0.5, height_in=48.0, y_center_in=25.0)
    assert p.y_bottom_in == pytest.approx(1.0)
    assert p.y_top_in == pytest.approx(49.0)
    assert p.y_top_in - p.y_bottom_in == pytest.approx(p.height_in)


def test_a_plate_is_frozen() -> None:
    p = Plate("bf", width_in=14.0, height_in=0.75, y_center_in=0.375)
    with pytest.raises(AttributeError):
        p.width_in = 15.0  # type: ignore[misc]


def test_moving_a_plate_keeps_its_size() -> None:
    p = Plate("tf", width_in=14.0, height_in=1.25, y_center_in=50.0)
    moved = p.moved_to(-3.0)
    assert moved.y_center_in == -3.0
    assert moved.area_in2 == p.area_in2
    assert moved.label == p.label


@pytest.mark.parametrize("width_in,height_in", [(0.0, 1.0), (1.0, 0.0), (-2.0, 1.0), (1.0, -2.0)])
def test_a_plate_with_no_material_is_refused(width_in: float, height_in: float) -> None:
    with pytest.raises(GeometryError):
        Plate("bad", width_in=width_in, height_in=height_in, y_center_in=0.0)


def test_a_plate_needs_a_label() -> None:
    with pytest.raises(GeometryError):
        Plate("   ", width_in=1.0, height_in=1.0, y_center_in=0.0)


def test_the_error_names_the_plate_that_was_wrong() -> None:
    with pytest.raises(GeometryError, match="bottom flange"):
        Plate("bottom flange", width_in=14.0, height_in=0.0, y_center_in=0.0)


def test_corrosion_takes_the_thickness_of_a_flange() -> None:
    f = flange("bf", width_in=14.0, thickness_in=0.75, y_center_in=0.375)
    thinned = f.thinned_by(0.125)
    assert thinned.height_in == pytest.approx(0.625)
    assert thinned.width_in == pytest.approx(14.0)


def test_corrosion_takes_the_thickness_of_a_web() -> None:
    w = web("web", thickness_in=0.4375, depth_in=54.0, y_center_in=27.75)
    thinned = w.thinned_by(0.0625)
    assert thinned.width_in == pytest.approx(0.375)
    assert thinned.height_in == pytest.approx(54.0)


def test_a_loss_that_eats_the_plate_is_refused() -> None:
    w = web("web", thickness_in=0.375, depth_in=54.0, y_center_in=27.0)
    with pytest.raises(GeometryError, match="removes the whole plate"):
        w.thinned_by(0.375)


def test_a_negative_loss_is_refused_rather_than_adding_steel() -> None:
    f = flange("bf", width_in=14.0, thickness_in=0.75, y_center_in=0.375)
    with pytest.raises(GeometryError, match="negative"):
        f.thinned_by(-0.05)


def test_zero_loss_returns_an_equal_plate() -> None:
    f = flange("bf", width_in=14.0, thickness_in=0.75, y_center_in=0.375)
    assert f.thinned_by(0.0) == f


def test_the_helpers_place_thickness_where_a_drawing_puts_it() -> None:
    f = flange("tf", width_in=16.0, thickness_in=1.5, y_center_in=55.0)
    assert (f.width_in, f.height_in) == (16.0, 1.5)
    w = web("web", thickness_in=0.5, depth_in=52.0, y_center_in=28.0)
    assert (w.width_in, w.height_in) == (0.5, 52.0)
