"""The vehicle catalogue, checked against the gross weights it is known by."""

from __future__ import annotations

import pytest

from shearstud.errors import ConfigError
from shearstud.loads import vehicles

pytestmark = pytest.mark.loads

PUBLISHED_GROSS_KIP = {
    "HL93-TRUCK": 72.0,
    "HL93-TANDEM": 50.0,
    "TYPE3": 50.0,
    "TYPE3S2": 72.0,
    "TYPE3-3": 80.0,
    "NRL": 80.0,
    "SU4": 54.0,
    "SU5": 62.0,
    "SU6": 69.5,
    "SU7": 77.5,
    "EV2": 57.5,
    "EV3": 86.0,
}


@pytest.mark.parametrize("name,gross_kip", sorted(PUBLISHED_GROSS_KIP.items()))
def test_every_vehicle_weighs_what_it_is_known_by(name: str, gross_kip: float) -> None:
    assert vehicles.vehicle(name).gross_kip == pytest.approx(gross_kip)


def test_the_catalogue_covers_exactly_the_published_list() -> None:
    assert set(vehicles.names()) == set(PUBLISHED_GROSS_KIP)


def test_lookup_forgives_case_and_padding() -> None:
    assert vehicles.vehicle("type3s2") is vehicles.vehicle("  TYPE3S2  ")


def test_an_unknown_vehicle_names_itself() -> None:
    with pytest.raises(ConfigError, match="unknown vehicle 'HS15'"):
        vehicles.vehicle("HS15")


def test_an_unknown_vehicle_class_is_refused_on_lookup() -> None:
    with pytest.raises(ConfigError, match="unknown vehicle"):
        vehicles.vehicle_class("HS15")


@pytest.mark.parametrize(
    "name,expected",
    [
        ("HL93-TRUCK", vehicles.CLASS_DESIGN),
        ("TYPE3-3", vehicles.CLASS_LEGAL),
        ("SU7", vehicles.CLASS_SHV),
        ("EV3", vehicles.CLASS_EMERGENCY),
    ],
)
def test_each_vehicle_knows_its_class(name: str, expected: str) -> None:
    assert vehicles.vehicle_class(name) == expected


def test_every_class_has_at_least_one_vehicle() -> None:
    for cls in vehicles.CLASSES:
        assert vehicles.names(cls)


def test_the_classes_partition_the_catalogue() -> None:
    covered: list[str] = []
    for cls in vehicles.CLASSES:
        covered.extend(vehicles.names(cls))
    assert sorted(covered) == sorted(vehicles.names())


def test_an_unknown_class_is_refused_when_filtering() -> None:
    with pytest.raises(ConfigError, match="unknown vehicle class"):
        vehicles.names("permit")


def test_the_legal_fleet_is_the_legal_and_shv_classes() -> None:
    fleet = {t.name for t in vehicles.legal_fleet()}
    assert fleet == set(vehicles.names(vehicles.CLASS_LEGAL)) | set(
        vehicles.names(vehicles.CLASS_SHV)
    )


def test_the_legal_fleet_leaves_out_the_design_vehicles() -> None:
    fleet = {t.name for t in vehicles.legal_fleet()}
    assert "HL93-TRUCK" not in fleet
    assert "EV3" not in fleet


def test_the_design_truck_defaults_to_the_tight_rear_gap() -> None:
    t = vehicles.design_truck()
    assert t.length_ft == pytest.approx(28.0)
    assert t.gross_kip == pytest.approx(72.0)


def test_the_design_truck_stretches_to_thirty_feet() -> None:
    t = vehicles.design_truck(30.0)
    assert t.length_ft == pytest.approx(44.0)
    assert t.gross_kip == pytest.approx(72.0)


def test_stretching_the_rear_gap_leaves_the_front_gap_alone() -> None:
    assert vehicles.design_truck(22.0).offsets_ft == pytest.approx((0.0, 14.0, 36.0))


@pytest.mark.parametrize("gap_ft", [13.9, 30.1, 0.0, 100.0])
def test_a_rear_gap_outside_the_range_is_refused(gap_ft: float) -> None:
    with pytest.raises(ConfigError, match="outside 14.0 to 30.0"):
        vehicles.design_truck(gap_ft)


def test_the_tandem_is_two_axles_four_feet_apart() -> None:
    t = vehicles.vehicle("HL93-TANDEM")
    assert t.axle_count == 2
    assert t.length_ft == pytest.approx(4.0)


def test_the_legal_semi_is_five_axles_over_forty_one_feet() -> None:
    t = vehicles.vehicle("TYPE3S2")
    assert t.axle_count == 5
    assert t.length_ft == pytest.approx(41.0)


def test_type_three_three_is_the_longest_legal_vehicle() -> None:
    legal = [vehicles.vehicle(n) for n in vehicles.names(vehicles.CLASS_LEGAL)]
    longest = max(legal, key=lambda t: t.length_ft)
    assert longest.name == "TYPE3-3"


def test_every_catalogue_vehicle_has_a_plausible_heaviest_axle() -> None:
    for name in vehicles.names():
        t = vehicles.vehicle(name)
        assert 8.0 <= t.heaviest_axle_kip <= 34.0, name


def test_every_catalogue_vehicle_is_at_least_two_axles_except_none() -> None:
    for name in vehicles.names():
        assert vehicles.vehicle(name).axle_count >= 2, name


def test_the_lane_load_is_the_published_value() -> None:
    assert pytest.approx(0.64) == vehicles.DESIGN_LANE_KLF
