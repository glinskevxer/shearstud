"""Strain records: the container everything downstream reads."""

from __future__ import annotations

import math
from datetime import datetime, timedelta

import pytest

from shearstud.errors import RecordError
from shearstud.signals.series import StrainRecord

pytestmark = pytest.mark.signals

START = datetime(2025, 6, 11, 5, 30, 0)


def record(samples: list[float], rate_hz: float = 100.0) -> StrainRecord:
    return StrainRecord(
        gauge_id="G3-BF-01",
        started_at=START,
        sample_rate_hz=rate_hz,
        samples_ue=tuple(samples),
    )


def ramp(count: int = 100) -> StrainRecord:
    return record([float(i) for i in range(count)])


def test_a_record_reports_its_length_two_ways() -> None:
    r = ramp(64)
    assert len(r) == 64
    assert r.sample_count == 64


def test_the_interval_is_the_reciprocal_of_the_rate() -> None:
    assert record([0.0] * 16, rate_hz=200.0).interval_s == pytest.approx(0.005)


def test_duration_counts_intervals_not_samples() -> None:
    # Ten samples at 100 Hz span nine intervals, which is 0.09 seconds.
    assert record([0.0] * 10).duration_s == pytest.approx(0.09)


def test_the_end_timestamp_is_the_start_plus_the_duration() -> None:
    r = record([0.0] * 101)
    assert r.ended_at == START + timedelta(seconds=1.0)


def test_sample_times_run_from_zero() -> None:
    r = ramp()
    assert r.time_of(0) == pytest.approx(0.0)
    assert r.time_of(50) == pytest.approx(0.5)


def test_sample_timestamps_track_the_start() -> None:
    r = ramp()
    assert r.timestamp_of(25) == START + timedelta(seconds=0.25)


def test_asking_for_a_sample_that_is_not_there_is_refused() -> None:
    with pytest.raises(RecordError, match="no sample 500 in 100"):
        ramp().time_of(500)


def test_index_lookup_rounds_to_the_nearest_sample() -> None:
    r = ramp()
    assert r.index_at(0.253) == 25
    assert r.index_at(0.257) == 26


def test_index_lookup_clamps_rather_than_raising() -> None:
    r = ramp()
    assert r.index_at(-5.0) == 0
    assert r.index_at(500.0) == 99


def test_the_summary_statistics_of_a_ramp() -> None:
    r = ramp(101)
    assert r.mean_ue == pytest.approx(50.0)
    assert r.peak_ue == pytest.approx(100.0)
    assert r.trough_ue == pytest.approx(0.0)
    assert r.range_ue == pytest.approx(100.0)


def test_rms_is_taken_about_zero_not_about_the_mean() -> None:
    r = record([3.0] * 16)
    assert r.rms_ue == pytest.approx(3.0)
    assert r.mean_ue == pytest.approx(3.0)


def test_rms_of_a_symmetric_signal_is_not_its_mean() -> None:
    r = record([-4.0, 4.0] * 8)
    assert r.mean_ue == pytest.approx(0.0)
    assert r.rms_ue == pytest.approx(4.0)


def test_the_standard_deviation_of_a_flat_record_is_zero() -> None:
    assert record([7.5] * 20).standard_deviation_ue() == pytest.approx(0.0)


def test_the_standard_deviation_grows_with_the_spread() -> None:
    tight = record([0.0, 1.0] * 16).standard_deviation_ue()
    wide = record([0.0, 40.0] * 16).standard_deviation_ue()
    assert wide > tight


def test_shifting_moves_the_mean_and_leaves_the_range() -> None:
    r = ramp(101)
    shifted = r.shifted_by(-50.0)
    assert shifted.mean_ue == pytest.approx(0.0)
    assert shifted.range_ue == pytest.approx(r.range_ue)


def test_shifting_keeps_the_gauge_and_the_clock() -> None:
    shifted = ramp().shifted_by(12.0)
    assert shifted.gauge_id == "G3-BF-01"
    assert shifted.started_at == START


def test_a_window_starts_where_it_was_asked_to() -> None:
    r = ramp()
    w = r.window(0.20, 0.60)
    assert w.started_at == START + timedelta(seconds=0.20)
    assert w.sample_count == 41
    assert w.samples_ue[0] == pytest.approx(20.0)


def test_a_window_keeps_the_sample_rate() -> None:
    assert ramp().window(0.1, 0.5).sample_rate_hz == pytest.approx(100.0)


def test_a_backwards_window_is_refused() -> None:
    with pytest.raises(RecordError, match="has no length"):
        ramp().window(0.6, 0.2)


def test_a_window_too_short_to_be_a_record_is_refused() -> None:
    with pytest.raises(RecordError, match="holds 3 samples"):
        ramp().window(0.10, 0.12)


def test_decimating_thins_the_samples_and_the_rate_together() -> None:
    r = ramp(100)
    d = r.decimated(4)
    assert d.sample_count == 25
    assert d.sample_rate_hz == pytest.approx(25.0)
    assert d.duration_s == pytest.approx(24.0 / 25.0)


def test_decimating_by_one_hands_back_the_same_record() -> None:
    r = ramp()
    assert r.decimated(1) is r


def test_decimating_keeps_the_samples_that_were_recorded() -> None:
    d = ramp(100).decimated(10)
    assert list(d.samples_ue) == [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]


def test_a_decimation_factor_below_one_is_refused() -> None:
    with pytest.raises(RecordError, match="is not a factor"):
        ramp().decimated(0)


def test_a_record_needs_a_gauge_id() -> None:
    with pytest.raises(RecordError, match="needs a gauge id"):
        StrainRecord(gauge_id=" ", started_at=START, sample_rate_hz=100.0, samples_ue=(0.0,) * 16)


@pytest.mark.parametrize("rate_hz", [0.5, 0.0, 5000.0, -100.0])
def test_a_sample_rate_off_the_chart_is_refused(rate_hz: float) -> None:
    with pytest.raises(RecordError, match="sample rate"):
        record([0.0] * 16, rate_hz=rate_hz)


def test_a_record_too_short_to_hold_an_event_is_refused() -> None:
    with pytest.raises(RecordError, match="4 samples is shorter"):
        record([0.0] * 4)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_sample_that_is_not_a_number_is_refused(bad: float) -> None:
    samples = [0.0] * 16
    samples[9] = bad
    with pytest.raises(RecordError, match="sample 9 is not a number"):
        record(samples)


def test_a_record_of_all_zeroes_is_still_a_valid_record() -> None:
    r = record([0.0] * 32)
    assert r.range_ue == 0.0
    assert math.isfinite(r.rms_ue)
