"""Member capacity, checked against shapes whose answers are known by hand."""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.geometry.plate import Plate, flange, web
from shearstud.geometry.section import Section
from shearstud.rating import capacity as cap

pytestmark = pytest.mark.rating


def solid_bar(width_in: float = 6.0, depth_in: float = 12.0) -> Section:
    return Section(
        "bar",
        (
            Plate("bottom", width_in, depth_in / 2.0, depth_in / 4.0),
            Plate("web", width_in, 0.001, depth_in / 2.0),
            Plate("top", width_in, depth_in / 2.0, 3.0 * depth_in / 4.0),
        ),
    )


def stocky_girder() -> Section:
    """A thick web that is comfortably compact."""
    return Section(
        "PG36",
        (
            flange("bottom", width_in=16.0, thickness_in=1.5, y_center_in=0.75),
            web("web", thickness_in=1.0, depth_in=36.0, y_center_in=19.5),
            flange("top", width_in=16.0, thickness_in=1.5, y_center_in=38.25),
        ),
    )


def slender_girder() -> Section:
    """A deep thin web the way a 1962 plate girder was detailed."""
    return Section(
        "PG84",
        (
            flange("bottom", width_in=18.0, thickness_in=1.5, y_center_in=0.75),
            web("web", thickness_in=0.375, depth_in=84.0, y_center_in=43.5),
            flange("top", width_in=18.0, thickness_in=1.5, y_center_in=86.25),
        ),
    )


@pytest.mark.parametrize(
    "grade,fy", [("A36", 36.0), ("A7", 33.0), ("A572-50", 50.0), ("A709-70", 70.0)]
)
def test_the_grades_carry_their_published_yield(grade: str, fy: float) -> None:
    assert cap.yield_stress_ksi(grade) == pytest.approx(fy)


def test_grade_lookup_forgives_case_and_padding() -> None:
    assert cap.yield_stress_ksi(" a36 ") == pytest.approx(36.0)


def test_an_unknown_grade_is_refused() -> None:
    with pytest.raises(InputError, match="unknown steel grade"):
        cap.yield_stress_ksi("A992-65")


def test_web_slenderness_is_depth_over_thickness() -> None:
    assert cap.web_slenderness(slender_girder()) == pytest.approx(84.0 / 0.375)


def test_a_thick_web_is_compact() -> None:
    assert cap.is_compact_web(stocky_girder(), 50.0)


def test_a_thin_deep_web_is_not() -> None:
    assert not cap.is_compact_web(slender_girder(), 50.0)


def test_a_higher_yield_makes_compactness_harder() -> None:
    section = Section(
        "borderline",
        (
            flange("bottom", width_in=16.0, thickness_in=1.5, y_center_in=0.75),
            web("web", thickness_in=0.5, depth_in=45.0, y_center_in=24.0),
            flange("top", width_in=16.0, thickness_in=1.5, y_center_in=47.25),
        ),
    )
    assert cap.is_compact_web(section, 36.0)
    assert not cap.is_compact_web(section, 70.0)


def test_a_yield_stress_of_zero_is_refused_by_the_compactness_check() -> None:
    with pytest.raises(InputError, match="is not a stress"):
        cap.is_compact_web(stocky_girder(), 0.0)


def test_the_yield_moment_is_the_modulus_times_the_stress() -> None:
    section = stocky_girder()
    got = cap.yield_moment_kipft(section, 50.0)
    assert got == pytest.approx(section.section_modulus_bottom_in3 * 50.0 / 12.0)


def test_the_yield_moment_can_be_taken_at_the_top_fibre() -> None:
    section = slender_girder()
    top = cap.yield_moment_kipft(section, 50.0, fibre="top")
    bottom = cap.yield_moment_kipft(section, 50.0, fibre="bottom")
    assert top == pytest.approx(bottom)


def test_an_unknown_fibre_is_refused() -> None:
    with pytest.raises(InputError, match="expected top or bottom"):
        cap.yield_moment_kipft(stocky_girder(), 50.0, fibre="middle")


def test_a_yield_stress_of_zero_is_refused_by_the_yield_moment() -> None:
    with pytest.raises(InputError, match="is not a stress"):
        cap.yield_moment_kipft(stocky_girder(), 0.0)


def test_the_plastic_axis_of_a_symmetric_section_is_mid_depth() -> None:
    section = stocky_girder()
    assert cap.plastic_neutral_axis_in(section) == pytest.approx(section.depth_in / 2.0, abs=0.05)


def test_the_plastic_axis_moves_towards_the_heavier_flange() -> None:
    section = Section(
        "heavy bottom",
        (
            flange("bottom", width_in=20.0, thickness_in=2.5, y_center_in=1.25),
            web("web", thickness_in=0.5, depth_in=48.0, y_center_in=26.5),
            flange("top", width_in=12.0, thickness_in=1.0, y_center_in=51.0),
        ),
    )
    assert cap.plastic_neutral_axis_in(section) < section.depth_in / 2.0


def test_the_plastic_axis_splits_the_area_in_half() -> None:
    section = slender_girder()
    axis = cap.plastic_neutral_axis_in(section)
    below = sum(
        p.width_in * (min(p.y_top_in, axis) - p.y_bottom_in)
        for p in section
        if min(p.y_top_in, axis) > p.y_bottom_in
    )
    assert below == pytest.approx(section.area_in2 / 2.0, rel=1e-6)


def test_the_plastic_moment_of_a_rectangle_is_the_closed_form() -> None:
    # A solid rectangle has Zx = bd^2/4, so Mp = Fy b d^2 / 4.
    section = solid_bar(width_in=6.0, depth_in=12.0)
    got = cap.plastic_moment_kipft(section, 36.0)
    assert got == pytest.approx(36.0 * 6.0 * 144.0 / 4.0 / 12.0, rel=0.01)


def test_the_plastic_moment_beats_the_yield_moment() -> None:
    section = stocky_girder()
    assert cap.plastic_moment_kipft(section, 50.0) > cap.yield_moment_kipft(section, 50.0)


def test_the_shape_factor_of_a_girder_is_modest() -> None:
    # A plate girder is nearly all flange, so its shape factor sits just above
    # one. A solid rectangle gets 1.5.
    section = stocky_girder()
    factor = cap.plastic_moment_kipft(section, 50.0) / cap.yield_moment_kipft(section, 50.0)
    assert 1.0 < factor < 1.3


def test_a_yield_stress_of_zero_is_refused_by_the_plastic_moment() -> None:
    with pytest.raises(InputError, match="is not a stress"):
        cap.plastic_moment_kipft(stocky_girder(), 0.0)


def test_a_compact_composite_section_gets_the_plastic_mechanism() -> None:
    got = cap.flexural_capacity(stocky_girder(), "A572-50", composite=True)
    assert got.mechanism == "plastic"
    assert got.is_compact
    assert got.yield_stress_ksi == pytest.approx(50.0)


def test_a_non_composite_section_gets_the_yield_mechanism() -> None:
    got = cap.flexural_capacity(stocky_girder(), "A572-50", composite=False)
    assert got.mechanism == "yield"


def test_a_slender_web_gets_the_yield_mechanism_even_when_composite() -> None:
    got = cap.flexural_capacity(slender_girder(), "A572-50", composite=True)
    assert got.mechanism == "yield"
    assert not got.is_compact


def test_the_plastic_mechanism_reports_the_larger_capacity() -> None:
    plastic = cap.flexural_capacity(stocky_girder(), "A572-50", composite=True)
    elastic = cap.flexural_capacity(stocky_girder(), "A572-50", composite=False)
    assert plastic.moment_kipft > elastic.moment_kipft


def test_a_stocky_web_reaches_its_full_plastic_shear() -> None:
    got = cap.shear_capacity_kip(stocky_girder(), "A36")
    assert got == pytest.approx(0.58 * 36.0 * 36.0 * 1.0)


def test_a_slender_web_cannot() -> None:
    section = slender_girder()
    plastic = 0.58 * 50.0 * 84.0 * 0.375
    assert cap.shear_capacity_kip(section, "A572-50") < 0.5 * plastic


def test_stiffeners_raise_the_shear_capacity_of_a_slender_web() -> None:
    section = slender_girder()
    bare = cap.shear_capacity_kip(section, "A572-50")
    stiffened = cap.shear_capacity_kip(section, "A572-50", stiffener_spacing_ft=5.0)
    assert stiffened > bare


def test_closer_stiffeners_help_more() -> None:
    section = slender_girder()
    wide = cap.shear_capacity_kip(section, "A572-50", stiffener_spacing_ft=12.0)
    tight = cap.shear_capacity_kip(section, "A572-50", stiffener_spacing_ft=4.0)
    assert tight > wide


def test_a_stiffener_spacing_of_zero_is_refused() -> None:
    with pytest.raises(InputError, match="is not a spacing"):
        cap.shear_capacity_kip(slender_girder(), "A36", stiffener_spacing_ft=0.0)


def test_the_buckling_ratio_is_one_for_a_stocky_web() -> None:
    assert cap.shear_buckling_ratio(30.0, 50.0, 5.0) == pytest.approx(1.0)


def test_the_buckling_ratio_falls_off_with_slenderness() -> None:
    stocky = cap.shear_buckling_ratio(60.0, 50.0, 5.0)
    slender = cap.shear_buckling_ratio(200.0, 50.0, 5.0)
    assert 0.0 < slender < stocky <= 1.0


def test_the_buckling_ratio_is_continuous_at_the_first_limit() -> None:
    import math

    limit = 1.12 * math.sqrt(29000.0 * 5.0 / 50.0)
    below = cap.shear_buckling_ratio(limit - 0.001, 50.0, 5.0)
    above = cap.shear_buckling_ratio(limit + 0.001, 50.0, 5.0)
    assert below == pytest.approx(above, abs=1e-4)


def test_the_buckling_ratio_is_continuous_at_the_second_limit() -> None:
    import math

    limit = 1.40 * math.sqrt(29000.0 * 5.0 / 50.0)
    below = cap.shear_buckling_ratio(limit - 0.001, 50.0, 5.0)
    above = cap.shear_buckling_ratio(limit + 0.001, 50.0, 5.0)
    assert below == pytest.approx(above, abs=1e-3)


@pytest.mark.parametrize(
    "args,message",
    [
        ((0.0, 50.0, 5.0), "is not a ratio"),
        ((100.0, 0.0, 5.0), "is not a stress"),
        ((100.0, 50.0, 0.0), "is not a coefficient"),
    ],
)
def test_a_bad_buckling_input_is_refused(args: tuple[float, ...], message: str) -> None:
    with pytest.raises(InputError, match=message):
        cap.shear_buckling_ratio(*args)
