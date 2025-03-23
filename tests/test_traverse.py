"""Moving load traversal, checked against hand computed governing placements."""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.loads import traverse, vehicles
from shearstud.loads.axles import AxleTrain, train
from shearstud.loads.continuous import continuous_moment
from shearstud.loads.influence import simple_moment, simple_reaction, simple_shear

pytestmark = pytest.mark.loads


def single_axle(weight_kip: float = 10.0) -> AxleTrain:
    return train("single", [weight_kip], [])


def test_one_axle_on_a_midspan_line_reads_the_ordinate() -> None:
    il = simple_moment(80.0, 40.0)
    assert traverse.effect(il, single_axle(), 40.0) == pytest.approx(10.0 * 20.0)


def test_an_axle_off_the_span_contributes_nothing() -> None:
    il = simple_moment(80.0, 40.0)
    assert traverse.effect(il, single_axle(), 200.0) == pytest.approx(0.0)


def test_a_truck_reads_the_sum_of_its_axles() -> None:
    il = simple_moment(100.0, 50.0)
    t = vehicles.design_truck()
    by_hand = 8.0 * il.at(50.0) + 32.0 * il.at(36.0) + 32.0 * il.at(22.0)
    assert traverse.effect(il, t, 50.0) == pytest.approx(by_hand)


def test_the_governing_placement_of_one_axle_is_the_peak() -> None:
    il = simple_moment(80.0, 30.0)
    placement = traverse.worst_effect(il, single_axle())
    assert placement.value == pytest.approx(10.0 * il.peak)
    assert placement.lead_position_ft == pytest.approx(30.0)


def test_the_design_truck_on_an_eighty_foot_span_governs_with_the_drive_axle_at_midspan() -> None:
    # Middle axle on the peak: ordinates 13, 20, 13 under 8, 32, 32 kip.
    il = simple_moment(80.0, 40.0)
    placement = traverse.worst_effect(il, vehicles.design_truck())
    assert placement.value == pytest.approx(8.0 * 13.0 + 32.0 * 20.0 + 32.0 * 13.0)
    assert placement.lead_position_ft == pytest.approx(54.0)


def test_putting_the_rear_axle_at_midspan_is_worse_than_the_drive_axle() -> None:
    il = simple_moment(80.0, 40.0)
    best = traverse.worst_effect(il, vehicles.design_truck()).value
    rear_at_midspan = traverse.effect(il, vehicles.design_truck(), 68.0)
    assert rear_at_midspan < best


def test_a_short_span_only_fits_part_of_the_truck() -> None:
    il = simple_moment(20.0, 10.0)
    placement = traverse.worst_effect(il, vehicles.design_truck())
    # One 32 kip axle at midspan is 160, and the other axles are off the span.
    assert placement.value == pytest.approx(160.0, rel=1e-6)


def test_the_worst_placement_is_at_least_as_good_as_any_scan_position() -> None:
    il = simple_moment(96.0, 38.0)
    t = vehicles.vehicle("TYPE3S2")
    best = traverse.worst_effect(il, t).value
    for step in range(0, 1400):
        assert traverse.effect(il, t, step * 0.1) <= best + 1e-9


def test_reversing_matters_on_an_unsymmetric_line() -> None:
    il = simple_moment(90.0, 20.0)
    t = vehicles.vehicle("TYPE3S2")
    one_way = traverse.worst_effect(il, t, both_ways=False)
    both_ways = traverse.worst_effect(il, t, both_ways=True)
    assert both_ways.value >= one_way.value


def test_the_placement_says_which_way_the_truck_was_facing() -> None:
    il = simple_moment(90.0, 20.0)
    placement = traverse.worst_effect(il, vehicles.vehicle("TYPE3S2"))
    assert placement.direction in {"ahead", "back"}
    assert placement.direction == ("back" if placement.reversed_travel else "ahead")


def test_the_placement_carries_the_vehicle_name_not_the_reversed_one() -> None:
    il = simple_moment(90.0, 20.0)
    placement = traverse.worst_effect(il, vehicles.vehicle("TYPE3S2"))
    assert placement.vehicle == "TYPE3S2"


def test_asking_for_a_minimum_finds_the_negative_side() -> None:
    il = continuous_moment([100.0, 100.0], 0, 50.0)
    worst_positive = traverse.worst_effect(il, vehicles.design_truck(), maximum=True)
    worst_negative = traverse.worst_effect(il, vehicles.design_truck(), maximum=False)
    assert worst_positive.value > 0.0
    assert worst_negative.value < 0.0


def test_a_shear_line_governs_with_an_axle_right_at_the_section() -> None:
    il = simple_shear(60.0, 0.0)
    placement = traverse.worst_effect(il, single_axle())
    assert placement.value == pytest.approx(10.0)
    assert placement.lead_position_ft == pytest.approx(0.0)


def test_the_reaction_line_gives_the_full_axle_at_the_bearing() -> None:
    il = simple_reaction(70.0)
    placement = traverse.worst_effect(il, vehicles.vehicle("HL93-TANDEM"))
    # 25 kip at the bearing plus 25 kip four feet in.
    assert placement.value == pytest.approx(25.0 + 25.0 * (66.0 / 70.0))


def test_an_envelope_picks_the_worst_vehicle() -> None:
    il = simple_moment(60.0, 30.0)
    fleet = vehicles.legal_fleet()
    best = traverse.envelope(il, fleet)
    for t in fleet:
        assert traverse.worst_effect(il, t).value <= best.value + 1e-9


def test_an_envelope_names_the_vehicle_that_governed() -> None:
    il = simple_moment(60.0, 30.0)
    best = traverse.envelope(il, vehicles.legal_fleet())
    assert best.vehicle in {t.name for t in vehicles.legal_fleet()}


def test_an_empty_envelope_is_refused() -> None:
    with pytest.raises(InputError, match="at least one vehicle"):
        traverse.envelope(simple_moment(60.0, 30.0), [])


def test_a_lane_load_on_a_simple_span_is_the_whole_area() -> None:
    il = simple_moment(80.0, 40.0)
    assert traverse.uniform_effect(il, 0.64) == pytest.approx(0.64 * 80.0**2 / 8.0)


def test_a_lane_load_placed_adversely_beats_laying_it_everywhere() -> None:
    il = continuous_moment([100.0, 100.0], 0, 50.0)
    adverse = traverse.uniform_effect(il, 0.64, adverse_only=True)
    everywhere = traverse.uniform_effect(il, 0.64, adverse_only=False)
    assert adverse > everywhere


def test_the_negative_lane_placement_is_negative() -> None:
    il = continuous_moment([100.0, 100.0], 0, 50.0)
    assert traverse.uniform_effect_negative(il, 0.64) < 0.0


@pytest.mark.parametrize("fn", [traverse.uniform_effect, traverse.uniform_effect_negative])
def test_a_negative_lane_load_is_refused(fn: object) -> None:
    il = simple_moment(80.0, 40.0)
    with pytest.raises(InputError, match="is negative"):
        fn(il, -0.64)  # type: ignore[operator]


def test_a_vehicle_longer_than_the_line_still_finds_a_placement() -> None:
    il = simple_moment(15.0, 7.5)
    placement = traverse.worst_effect(il, vehicles.vehicle("TYPE3-3"))
    assert placement.value > 0.0
