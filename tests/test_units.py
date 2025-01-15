"""The unit layer is arithmetic plus a naming rule, and both are asserted here."""

from __future__ import annotations

import pytest

from shearstud import units
from shearstud.errors import UnitError

pytestmark = pytest.mark.geometry


def test_a_foot_is_twelve_inches_in_both_directions() -> None:
    assert units.ft_to_in(1.0) == 12.0
    assert units.in_to_ft(12.0) == 1.0


def test_length_conversion_round_trips_for_an_awkward_span() -> None:
    span_ft = 87.375
    assert units.in_to_ft(units.ft_to_in(span_ft)) == pytest.approx(span_ft)


def test_a_mile_is_the_number_a_traffic_count_uses() -> None:
    assert units.mi_to_ft(1.0) == 5280.0


def test_moment_conversion_round_trips() -> None:
    moment_kipft = 1432.5
    assert units.kipin_to_kipft(units.kipft_to_kipin(moment_kipft)) == pytest.approx(moment_kipft)


def test_one_hundred_microstrain_in_steel_is_two_point_nine_ksi() -> None:
    # 100e-6 * 29000 = 2.9, the number an inspector does in their head.
    assert units.strain_to_stress_ksi(100.0) == pytest.approx(2.9)


def test_stress_and_strain_are_inverse() -> None:
    strain_ue = 213.7
    stress_ksi = units.strain_to_stress_ksi(strain_ue)
    assert units.stress_to_strain_ue(stress_ksi) == pytest.approx(strain_ue)


def test_a_softer_modulus_reads_more_strain_for_the_same_stress() -> None:
    stiff_ue = units.stress_to_strain_ue(10.0, modulus_ksi=29000.0)
    soft_ue = units.stress_to_strain_ue(10.0, modulus_ksi=10000.0)
    assert soft_ue > stiff_ue


def test_a_zero_modulus_is_refused_rather_than_dividing() -> None:
    with pytest.raises(UnitError):
        units.stress_to_strain_ue(10.0, modulus_ksi=0.0)


def test_a_negative_modulus_is_refused() -> None:
    with pytest.raises(UnitError):
        units.stress_to_strain_ue(10.0, modulus_ksi=-29000.0)


def test_a_forty_degree_rise_is_two_hundred_sixty_microstrain() -> None:
    assert units.thermal_strain_ue(40.0) == pytest.approx(260.0)


def test_thermal_strain_signs_follow_the_temperature() -> None:
    assert units.thermal_strain_ue(-15.0) < 0.0
    assert units.thermal_strain_ue(0.0) == 0.0


@pytest.mark.parametrize(
    "name,expected",
    [
        ("span_ft", "ft"),
        ("web_thickness_in", "in"),
        ("moment_kipft", "kipft"),
        ("section_modulus_in3", "in3"),
        ("range_ksi", "ksi"),
        ("peak_ue", "ue"),
        ("growth_pct", "pct"),
    ],
)
def test_unit_of_reads_the_suffix(name: str, expected: str) -> None:
    assert units.unit_of(name) == expected


@pytest.mark.parametrize("name", ["span", "thickness", "moment_kn", "value_", "peak_uE"])
def test_unit_of_refuses_a_name_with_no_registered_suffix(name: str) -> None:
    with pytest.raises(UnitError):
        units.unit_of(name)


def test_has_unit_answers_without_raising() -> None:
    assert units.has_unit("depth_in")
    assert not units.has_unit("depth")


def test_every_registered_suffix_has_a_description() -> None:
    for suffix, text in units.SUFFIXES.items():
        assert suffix.islower(), suffix
        assert text.strip(), suffix
