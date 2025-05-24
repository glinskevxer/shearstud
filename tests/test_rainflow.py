"""Rainflow counting, checked against the worked example in ASTM E1049.

That example is the whole reason this module is written out rather than
imported. If the published table comes back, the four point rule and the residue
handling are both right; if it does not, no amount of reasoning about the code
will settle it.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from shearstud.errors import RecordError
from shearstud.signals import rainflow
from shearstud.signals.rainflow import Cycle
from shearstud.signals.series import StrainRecord

pytestmark = pytest.mark.signals

#: The series from ASTM E1049-85 figure 6.
ASTM_SERIES = [-2.0, 1.0, -3.0, 5.0, -1.0, 3.0, -4.0, 4.0, -2.0]

#: What the standard's own table gives for it, as range to count.
ASTM_TABLE = {3.0: 0.5, 4.0: 1.5, 6.0: 0.5, 8.0: 1.0, 9.0: 0.5}


def tally(cycles: list[Cycle]) -> dict[float, float]:
    out: dict[float, float] = {}
    for cycle in cycles:
        key = round(cycle.range_ue, 9)
        out[key] = out.get(key, 0.0) + cycle.count
    return out


def test_the_astm_example_reproduces_the_published_table() -> None:
    cycles = rainflow.count_cycles(ASTM_SERIES, close_residue=False)
    assert tally(cycles) == pytest.approx(ASTM_TABLE)


def test_the_astm_example_totals_four_cycles() -> None:
    cycles = rainflow.count_cycles(ASTM_SERIES, close_residue=False)
    assert rainflow.total_count(cycles) == pytest.approx(4.0)


def test_the_astm_example_closes_one_full_cycle_before_the_residue() -> None:
    cycles = rainflow.count_cycles(ASTM_SERIES, close_residue=False)
    full = [c for c in cycles if not c.is_half]
    assert len(full) == 1
    assert full[0].range_ue == pytest.approx(4.0)
    assert full[0].mean_ue == pytest.approx(1.0)


def test_closing_the_residue_keeps_the_same_total_count() -> None:
    halves = rainflow.count_cycles(ASTM_SERIES, close_residue=False)
    closed = rainflow.count_cycles(ASTM_SERIES, close_residue=True)
    assert rainflow.total_count(closed) == pytest.approx(rainflow.total_count(halves))


def test_closing_the_residue_gives_no_half_cycles() -> None:
    closed = rainflow.count_cycles(ASTM_SERIES, close_residue=True)
    assert all(not cycle.is_half for cycle in closed)


def test_closing_the_residue_is_at_least_as_damaging() -> None:
    halves = rainflow.count_cycles(ASTM_SERIES, close_residue=False)
    closed = rainflow.count_cycles(ASTM_SERIES, close_residue=True)
    assert rainflow.equivalent_range_ue(closed) >= rainflow.equivalent_range_ue(halves)


def test_the_largest_range_survives_either_way() -> None:
    halves = rainflow.count_cycles(ASTM_SERIES, close_residue=False)
    closed = rainflow.count_cycles(ASTM_SERIES, close_residue=True)
    assert rainflow.largest_range_ue(halves) == pytest.approx(9.0)
    assert rainflow.largest_range_ue(closed) == pytest.approx(9.0)


def test_one_clean_triangle_is_one_cycle() -> None:
    cycles = rainflow.count_cycles([0.0, 10.0, 0.0, 10.0, 0.0], close_residue=False)
    assert rainflow.total_count(cycles) == pytest.approx(2.0)
    assert rainflow.largest_range_ue(cycles) == pytest.approx(10.0)


def test_a_flat_signal_has_no_cycles() -> None:
    assert rainflow.count_cycles([4.0] * 50) == []


def test_a_monotonic_ramp_has_no_closed_cycles() -> None:
    assert rainflow.count_cycles([float(i) for i in range(50)], close_residue=False) == []


def test_a_small_loop_inside_a_big_one_is_counted_separately() -> None:
    cycles = rainflow.count_cycles([0.0, 100.0, 60.0, 80.0, 20.0], close_residue=False)
    counted = tally(cycles)
    assert counted[20.0] == pytest.approx(1.0)
    assert 20.0 in counted


def test_the_inner_loop_carries_its_own_mean() -> None:
    cycles = rainflow.count_cycles([0.0, 100.0, 60.0, 80.0, 20.0], close_residue=False)
    inner = next(c for c in cycles if c.range_ue == pytest.approx(20.0))
    assert inner.mean_ue == pytest.approx(70.0)
    assert inner.peak_ue == pytest.approx(80.0)
    assert inner.trough_ue == pytest.approx(60.0)


def test_reversals_drop_the_points_in_between() -> None:
    got = rainflow.turning_points([0.0, 1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 3.0])
    assert got == [0.0, 3.0, 1.0, 3.0]


def test_repeated_values_do_not_become_reversals() -> None:
    got = rainflow.turning_points([0.0, 5.0, 5.0, 5.0, 0.0])
    assert got == [0.0, 5.0, 0.0]


def test_a_gate_removes_the_small_reversals() -> None:
    noisy = [0.0, 100.0, 98.0, 99.0, 0.0]
    assert rainflow.turning_points(noisy, gate_ue=5.0) == [0.0, 100.0, 0.0]


def test_a_gate_leaves_an_alternating_sequence_behind() -> None:
    noisy = [0.0, 50.0, 48.0, 52.0, 47.0, 100.0, 96.0, 99.0, 0.0]
    points = rainflow.turning_points(noisy, gate_ue=10.0)
    for a, b, c in zip(points, points[1:], points[2:], strict=False):
        assert (b - a) * (c - b) < 0.0


def test_a_gate_cuts_the_cycle_count() -> None:
    noisy = [0.0, 50.0, 45.0, 55.0, 40.0, 100.0, 95.0, 99.0, 0.0]
    without = rainflow.count_cycles(noisy, close_residue=False)
    with_gate = rainflow.count_cycles(noisy, gate_ue=12.0, close_residue=False)
    assert rainflow.total_count(with_gate) < rainflow.total_count(without)


def test_a_gate_does_not_touch_the_largest_range() -> None:
    noisy = [0.0, 50.0, 45.0, 55.0, 40.0, 100.0, 95.0, 99.0, 0.0]
    without = rainflow.count_cycles(noisy, close_residue=False)
    with_gate = rainflow.count_cycles(noisy, gate_ue=12.0, close_residue=False)
    assert rainflow.largest_range_ue(with_gate) == pytest.approx(rainflow.largest_range_ue(without))


def test_a_negative_gate_is_refused() -> None:
    with pytest.raises(RecordError, match="is negative"):
        rainflow.turning_points(ASTM_SERIES, gate_ue=-1.0)


def test_the_equivalent_range_of_one_size_is_that_size() -> None:
    cycles = [Cycle(range_ue=40.0, mean_ue=0.0, count=1.0)] * 6
    assert rainflow.equivalent_range_ue(cycles) == pytest.approx(40.0)


def test_the_equivalent_range_is_pulled_up_by_the_big_ones() -> None:
    mixed = [
        Cycle(range_ue=10.0, mean_ue=0.0, count=99.0),
        Cycle(range_ue=100.0, mean_ue=0.0, count=1.0),
    ]
    arithmetic_mean = (10.0 * 99.0 + 100.0) / 100.0
    assert rainflow.equivalent_range_ue(mixed) > arithmetic_mean


def test_the_equivalent_range_of_nothing_is_zero() -> None:
    assert rainflow.equivalent_range_ue([]) == 0.0
    assert rainflow.largest_range_ue([]) == 0.0


def test_a_larger_exponent_weights_the_big_cycles_harder() -> None:
    mixed = [
        Cycle(range_ue=10.0, mean_ue=0.0, count=99.0),
        Cycle(range_ue=100.0, mean_ue=0.0, count=1.0),
    ]
    assert rainflow.equivalent_range_ue(mixed, 5.0) > rainflow.equivalent_range_ue(mixed, 3.0)


def test_an_exponent_of_zero_is_refused() -> None:
    with pytest.raises(RecordError, match="is not positive"):
        rainflow.equivalent_range_ue([Cycle(1.0, 0.0, 1.0)], 0.0)


def test_a_negative_cycle_range_is_refused() -> None:
    with pytest.raises(RecordError, match="is negative"):
        Cycle(range_ue=-1.0, mean_ue=0.0, count=1.0)


def test_a_cycle_with_no_count_is_refused() -> None:
    with pytest.raises(RecordError, match="is not a count"):
        Cycle(range_ue=10.0, mean_ue=0.0, count=0.0)


def test_counting_a_record_reads_its_samples() -> None:
    record = StrainRecord(
        gauge_id="G1",
        started_at=datetime(2025, 9, 1, 12, 0, 0),
        sample_rate_hz=50.0,
        samples_ue=tuple(ASTM_SERIES),
    )
    from_record = rainflow.count_record(record, close_residue=False)
    from_series = rainflow.count_cycles(ASTM_SERIES, close_residue=False)
    assert tally(from_record) == pytest.approx(tally(from_series))
