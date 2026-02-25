"""The catalogue is data, so the tests check the data as much as the code."""

from __future__ import annotations

from pathlib import Path

import pytest

from shearstud.errors import ConfigError, GeometryError
from shearstud.geometry import rolled

pytestmark = pytest.mark.geometry


def test_the_catalogue_loads_and_is_not_empty() -> None:
    assert len(rolled.catalogue()) >= 20


def test_a_known_shape_comes_back_with_its_published_numbers() -> None:
    w = rolled.shape("W36X150")
    assert w.depth_in == pytest.approx(35.85)
    assert w.inertia_in4 == pytest.approx(9040.0)
    assert w.modulus_in3 == pytest.approx(504.0)


def test_lookup_forgives_case_and_spaces() -> None:
    assert rolled.shape("w36x150") is rolled.shape("W36 X 150")


def test_an_unknown_shape_names_itself_in_the_error() -> None:
    with pytest.raises(ConfigError, match="W99X999"):
        rolled.shape("W99X999")


def test_the_catalogue_is_cached_and_hands_back_the_same_objects() -> None:
    assert rolled.catalogue() is rolled.catalogue()


def test_designations_are_unique() -> None:
    names = rolled.designations()
    assert len(names) == len(set(names))


def test_every_designation_parses_as_a_w_shape() -> None:
    for name in rolled.designations():
        assert name.startswith("W"), name
        assert "X" in name, name


@pytest.mark.parametrize("designation", rolled.designations())
def test_the_idealisation_stays_inside_the_fillet_allowance(designation: str) -> None:
    w = rolled.shape(designation)
    assert w.idealisation_error_frac() < rolled.IDEALISATION_TOLERANCE_FRAC


@pytest.mark.parametrize("designation", rolled.designations())
def test_the_idealised_area_stays_inside_the_same_allowance(designation: str) -> None:
    w = rolled.shape(designation)
    error = abs(w.section().area_in2 - w.area_in2) / w.area_in2
    assert error < rolled.IDEALISATION_TOLERANCE_FRAC


@pytest.mark.parametrize("designation", rolled.designations())
def test_the_idealisation_is_always_light_not_heavy(designation: str) -> None:
    # Fillets add steel the three rectangles do not have, so the idealisation
    # can only ever come out low. A high answer means a bad row.
    w = rolled.shape(designation)
    assert w.section().inertia_in4 < w.inertia_in4
    assert w.section().area_in2 < w.area_in2


@pytest.mark.parametrize("designation", rolled.designations())
def test_the_published_modulus_agrees_with_inertia_over_half_depth(designation: str) -> None:
    w = rolled.shape(designation)
    implied = w.inertia_in4 / (w.depth_in / 2.0)
    assert implied == pytest.approx(w.modulus_in3, rel=0.02)


@pytest.mark.parametrize("designation", rolled.designations())
def test_a_rolled_section_is_doubly_symmetric(designation: str) -> None:
    s = rolled.shape(designation).section()
    assert s.c_top_in == pytest.approx(s.c_bottom_in)
    assert s.section_modulus_top_in3 == pytest.approx(s.section_modulus_bottom_in3)


def test_the_section_is_based_at_zero() -> None:
    s = rolled.shape("W24X84").section()
    assert s.y_bottom_in == pytest.approx(0.0)
    assert s.depth_in == pytest.approx(24.10)


def test_web_depth_excludes_both_flanges() -> None:
    w = rolled.shape("W30X116")
    assert w.web_depth_in == pytest.approx(30.01 - 2.0 * 0.850)


def test_deeper_shapes_carry_more_inertia() -> None:
    assert rolled.shape("W40X199").inertia_in4 > rolled.shape("W12X26").inertia_in4


def test_a_row_missing_a_column_is_reported_with_its_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad = tmp_path / "rolled_shapes.csv"
    bad.write_text("designation,depth_in\nW1X1,10.0\n", encoding="utf-8")
    monkeypatch.setattr(rolled, "CATALOGUE_PATH", bad)
    rolled.catalogue.cache_clear()
    with pytest.raises(ConfigError, match="line 2"):
        rolled.catalogue()
    rolled.catalogue.cache_clear()


def test_a_duplicate_designation_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    header = (
        "designation,depth_in,flange_width_in,flange_thickness_in,"
        "web_thickness_in,area_in2,inertia_in4,modulus_in3"
    )
    row = "W10X10,10.0,5.0,0.5,0.3,7.0,100.0,20.0"
    bad = tmp_path / "rolled_shapes.csv"
    bad.write_text(f"{header}\n{row}\n{row}\n", encoding="utf-8")
    monkeypatch.setattr(rolled, "CATALOGUE_PATH", bad)
    rolled.catalogue.cache_clear()
    with pytest.raises(ConfigError, match="duplicate designation"):
        rolled.catalogue()
    rolled.catalogue.cache_clear()


def test_a_missing_catalogue_file_is_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rolled, "CATALOGUE_PATH", tmp_path / "gone.csv")
    rolled.catalogue.cache_clear()
    with pytest.raises(ConfigError, match="missing"):
        rolled.catalogue()
    rolled.catalogue.cache_clear()


def test_an_empty_catalogue_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    header = (
        "designation,depth_in,flange_width_in,flange_thickness_in,"
        "web_thickness_in,area_in2,inertia_in4,modulus_in3"
    )
    empty = tmp_path / "rolled_shapes.csv"
    empty.write_text(header + "\n", encoding="utf-8")
    monkeypatch.setattr(rolled, "CATALOGUE_PATH", empty)
    rolled.catalogue.cache_clear()
    with pytest.raises(ConfigError, match="empty"):
        rolled.catalogue()
    rolled.catalogue.cache_clear()


def test_a_zero_thickness_row_fails_the_plate_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    header = (
        "designation,depth_in,flange_width_in,flange_thickness_in,"
        "web_thickness_in,area_in2,inertia_in4,modulus_in3"
    )
    row = "W10X10,10.0,5.0,0.0,0.3,7.0,100.0,20.0"
    bad = tmp_path / "rolled_shapes.csv"
    bad.write_text(f"{header}\n{row}\n", encoding="utf-8")
    monkeypatch.setattr(rolled, "CATALOGUE_PATH", bad)
    rolled.catalogue.cache_clear()
    with pytest.raises(GeometryError):
        rolled.catalogue()["W10X10"].section()
    rolled.catalogue.cache_clear()
