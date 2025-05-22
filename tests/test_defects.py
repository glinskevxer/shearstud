"""Dropouts, rail hits and spikes, and the one of the three that gets repaired."""

from __future__ import annotations

import math
from datetime import datetime

import pytest

from shearstud.errors import RecordError
from shearstud.signals import defects
from shearstud.signals.defects import Interval
from shearstud.signals.series import StrainRecord

pytestmark = pytest.mark.signals

START = datetime(2025, 8, 4, 9, 0, 0)


def strain(samples: list[float]) -> StrainRecord:
    return StrainRecord(
        gauge_id="G4-BF-02",
        started_at=START,
        sample_rate_hz=100.0,
        samples_ue=tuple(samples),
    )


def wiggle(count: int, amplitude: float = 20.0) -> list[float]:
    return [amplitude * math.sin(i * 0.31) for i in range(count)]


def test_an_interval_reports_its_length() -> None:
    assert Interval(10, 19).length == 10
    assert Interval(4, 4).length == 1


def test_intervals_know_when_they_overlap() -> None:
    assert Interval(0, 10).overlaps(Interval(10, 20))
    assert not Interval(0, 10).overlaps(Interval(11, 20))


def test_an_interval_can_be_timed_against_a_record() -> None:
    assert Interval(0, 49).seconds(strain(wiggle(100))) == pytest.approx(0.5)


def test_a_backwards_interval_is_refused() -> None:
    with pytest.raises(RecordError, match="runs backwards"):
        Interval(30, 10)


def test_an_interval_before_the_record_is_refused() -> None:
    with pytest.raises(RecordError, match="starts at -1"):
        Interval(-1, 10)


def test_a_lively_record_has_no_dropouts() -> None:
    assert defects.find_dropouts(strain(wiggle(400))) == []


def test_a_dead_stretch_is_found_with_its_bounds() -> None:
    samples = wiggle(400)
    for i in range(120, 220):
        samples[i] = samples[119]
    found = defects.find_dropouts(strain(samples))
    assert len(found) == 1
    assert found[0].first <= 121
    assert found[0].last >= 218


def test_a_short_flat_patch_is_not_a_dropout() -> None:
    samples = wiggle(400)
    for i in range(200, 210):
        samples[i] = samples[199]
    assert defects.find_dropouts(strain(samples)) == []


def test_a_completely_dead_channel_is_one_dropout() -> None:
    found = defects.find_dropouts(strain([12.0] * 300))
    assert len(found) == 1
    assert found[0].length == 300


def test_a_dropout_running_to_the_end_is_still_found() -> None:
    samples = wiggle(300) + [4.0] * 100
    found = defects.find_dropouts(strain(samples))
    assert found
    assert found[-1].last == 399


def test_two_dropouts_come_back_separately() -> None:
    samples = wiggle(600)
    for i in range(100, 200):
        samples[i] = samples[99]
    for i in range(400, 500):
        samples[i] = samples[399]
    assert len(defects.find_dropouts(strain(samples))) == 2


def test_a_negative_flat_tolerance_is_refused() -> None:
    with pytest.raises(RecordError, match="is negative"):
        defects.find_dropouts(strain(wiggle(100)), flat_tolerance_ue=-1.0)


def test_a_one_sample_dropout_is_refused_as_a_setting() -> None:
    with pytest.raises(RecordError, match="at least two samples"):
        defects.find_dropouts(strain(wiggle(100)), min_samples=1)


def test_a_record_inside_the_channel_range_has_no_rail_hits() -> None:
    assert defects.find_rail_hits(strain(wiggle(200, amplitude=50.0)), limit_ue=500.0) == []


def test_a_clipped_peak_is_a_rail_hit() -> None:
    samples = wiggle(300, amplitude=800.0)
    clipped = [max(-500.0, min(500.0, value)) for value in samples]
    found = defects.find_rail_hits(strain(clipped), limit_ue=500.0)
    assert found
    assert all(interval.length >= 2 for interval in found)


def test_a_rail_hit_at_the_end_of_the_record_is_found() -> None:
    samples = wiggle(200, amplitude=10.0) + [600.0] * 40
    found = defects.find_rail_hits(strain(samples), limit_ue=500.0)
    assert found[-1].last == 239


def test_a_single_sample_at_the_rail_can_be_ignored() -> None:
    samples = wiggle(200, amplitude=10.0)
    samples[100] = 600.0
    assert defects.find_rail_hits(strain(samples), limit_ue=500.0, min_samples=2) == []
    assert defects.find_rail_hits(strain(samples), limit_ue=500.0, min_samples=1)


def test_a_channel_limit_of_zero_is_refused() -> None:
    with pytest.raises(RecordError, match="is not a limit"):
        defects.find_rail_hits(strain(wiggle(100)), limit_ue=0.0)


def test_a_rail_hit_needs_at_least_one_sample() -> None:
    with pytest.raises(RecordError, match="at least one sample"):
        defects.find_rail_hits(strain(wiggle(100)), limit_ue=100.0, min_samples=0)


def test_a_clean_record_has_no_spikes() -> None:
    assert defects.find_spikes(strain(wiggle(400))) == []


def test_one_planted_spike_is_found() -> None:
    samples = wiggle(400)
    samples[213] += 900.0
    assert defects.find_spikes(strain(samples)) == [213]


def test_two_planted_spikes_are_both_found() -> None:
    samples = wiggle(400)
    samples[75] -= 700.0
    samples[300] += 700.0
    assert defects.find_spikes(strain(samples)) == [75, 300]


def test_a_spike_at_the_very_start_is_found() -> None:
    samples = wiggle(400)
    samples[0] += 900.0
    assert 0 in defects.find_spikes(strain(samples))


def test_a_huge_spike_does_not_raise_the_scale_past_itself() -> None:
    # The robust scale is a median, so one enormous sample cannot hide itself.
    samples = wiggle(400)
    samples[150] += 500000.0
    assert defects.find_spikes(strain(samples)) == [150]


def test_a_flat_record_has_no_scale_and_therefore_no_spikes() -> None:
    assert defects.find_spikes(strain([5.0] * 200)) == []


def test_despiking_repairs_the_sample_and_leaves_the_rest() -> None:
    clean = wiggle(400)
    samples = list(clean)
    samples[213] += 900.0
    repaired = defects.despike(strain(samples))
    assert repaired.samples_ue[213] == pytest.approx(clean[213], abs=15.0)
    assert repaired.samples_ue[100] == pytest.approx(clean[100])


def test_despiking_a_clean_record_hands_it_straight_back() -> None:
    r = strain(wiggle(400))
    assert defects.despike(r) is r


def test_despiking_cuts_the_range_back_to_the_real_signal() -> None:
    clean = strain(wiggle(400))
    samples = list(clean.samples_ue)
    samples[213] += 900.0
    assert defects.despike(strain(samples)).range_ue == pytest.approx(clean.range_ue, rel=0.2)


def test_a_spike_threshold_of_zero_is_refused() -> None:
    with pytest.raises(RecordError, match="is not a threshold"):
        defects.find_spikes(strain(wiggle(100)), threshold=0.0)


def test_a_spike_window_of_zero_is_refused() -> None:
    with pytest.raises(RecordError, match="too narrow"):
        defects.find_spikes(strain(wiggle(100)), half_window=0)


def test_merging_joins_touching_intervals() -> None:
    merged = defects.merge([Interval(0, 10), Interval(11, 20)])
    assert merged == [Interval(0, 20)]


def test_merging_leaves_a_real_gap_alone() -> None:
    merged = defects.merge([Interval(0, 10), Interval(20, 30)])
    assert len(merged) == 2


def test_merging_closes_a_gap_it_was_told_to() -> None:
    merged = defects.merge([Interval(0, 10), Interval(20, 30)], gap=10)
    assert merged == [Interval(0, 30)]


def test_merging_handles_a_contained_interval() -> None:
    assert defects.merge([Interval(0, 100), Interval(20, 30)]) == [Interval(0, 100)]


def test_merging_sorts_what_it_was_given() -> None:
    assert defects.merge([Interval(50, 60), Interval(0, 10)])[0].first == 0


def test_merging_nothing_gives_nothing() -> None:
    assert defects.merge([]) == []


def test_a_negative_merge_gap_is_refused() -> None:
    with pytest.raises(RecordError, match="is negative"):
        defects.merge([Interval(0, 1)], gap=-1)


def test_covered_samples_counts_an_overlap_once() -> None:
    assert defects.covered_samples([Interval(0, 99), Interval(50, 149)]) == 150


def test_covered_samples_of_nothing_is_zero() -> None:
    assert defects.covered_samples([]) == 0
