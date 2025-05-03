"""Signal conditioning, and the ordering claim the module makes for itself."""

from __future__ import annotations

import math
from datetime import datetime

import pytest

from shearstud.errors import RecordError
from shearstud.signals import conditioning as cond
from shearstud.signals.conditioning import TemperatureRecord
from shearstud.signals.series import StrainRecord

pytestmark = pytest.mark.signals

START = datetime(2025, 7, 2, 13, 15, 0)
RATE_HZ = 50.0


def strain(samples: list[float]) -> StrainRecord:
    return StrainRecord(
        gauge_id="G2-BF-04",
        started_at=START,
        sample_rate_hz=RATE_HZ,
        samples_ue=tuple(samples),
    )


def temperatures(samples: list[float]) -> TemperatureRecord:
    return TemperatureRecord(
        channel_id="T-01",
        started_at=START,
        sample_rate_hz=1.0,
        samples_degf=tuple(samples),
    )


def truck_event(count: int = 500, peak_ue: float = 120.0) -> list[float]:
    """A quiet lead in, one hump, a quiet lead out."""
    out = []
    for i in range(count):
        fraction = i / (count - 1)
        if 0.35 < fraction < 0.65:
            phase = (fraction - 0.35) / 0.30
            out.append(peak_ue * math.sin(math.pi * phase))
        else:
            out.append(0.0)
    return out


def test_removing_the_offset_centres_the_record() -> None:
    r = strain([10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0])
    assert cond.remove_offset(r).mean_ue == pytest.approx(0.0)


def test_removing_the_offset_leaves_the_range_alone() -> None:
    r = strain([10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 24.0])
    assert cond.remove_offset(r).range_ue == pytest.approx(r.range_ue)


def test_a_pure_ramp_fits_its_own_slope() -> None:
    samples = [3.0 * i / RATE_HZ for i in range(200)]
    slope_per_s, _ = cond.fit_drift(strain(samples))
    assert slope_per_s == pytest.approx(3.0)


def test_a_flat_record_has_no_slope() -> None:
    slope_per_s, intercept = cond.fit_drift(strain([7.0] * 64))
    assert slope_per_s == pytest.approx(0.0)
    assert intercept == pytest.approx(7.0)


def test_removing_drift_flattens_a_ramp_to_nothing() -> None:
    samples = [2.5 * i / RATE_HZ for i in range(300)]
    flattened = cond.remove_drift(strain(samples))
    assert flattened.range_ue == pytest.approx(0.0, abs=1e-9)


def test_removing_drift_keeps_the_event_it_was_hiding() -> None:
    event = truck_event()
    drifted = [value + 0.8 * i / RATE_HZ for i, value in enumerate(event)]
    flattened = cond.remove_drift(strain(drifted))
    assert flattened.range_ue == pytest.approx(strain(event).range_ue, rel=0.15)


def test_removing_drift_twice_changes_nothing_the_second_time() -> None:
    once = cond.remove_drift(strain(truck_event()))
    twice = cond.remove_drift(once)
    assert twice.samples_ue == pytest.approx(once.samples_ue, abs=1e-9)


def test_the_end_window_fit_beats_the_least_squares_fit_on_a_short_record() -> None:
    # One big event in a short record tilts a least squares line, and the end
    # window fit does not see the event at all.
    event = truck_event(count=300, peak_ue=200.0)
    drifted = [value + 1.0 * i / RATE_HZ for i, value in enumerate(event)]
    r = strain(drifted)
    by_ends = cond.remove_drift_by_ends(r, window_s=1.0)
    by_least_squares = cond.remove_drift(r)
    assert abs(by_ends.samples_ue[0]) < abs(by_least_squares.samples_ue[0])


def test_the_end_window_fit_leaves_the_quiet_ends_near_zero() -> None:
    event = truck_event(count=400)
    drifted = [value + 0.5 * i / RATE_HZ for i, value in enumerate(event)]
    corrected = cond.remove_drift_by_ends(strain(drifted), window_s=1.0)
    assert corrected.samples_ue[0] == pytest.approx(0.0, abs=1.0)
    assert corrected.samples_ue[-1] == pytest.approx(0.0, abs=1.0)


def test_an_end_window_that_does_not_fit_is_refused() -> None:
    with pytest.raises(RecordError, match="does not fit"):
        cond.remove_drift_by_ends(strain([0.0] * 20), window_s=5.0)


def test_a_window_of_no_length_is_refused() -> None:
    with pytest.raises(RecordError, match="is not a window"):
        cond.remove_drift_by_ends(strain([0.0] * 200), window_s=0.0)


def test_a_flat_temperature_channel_compensates_nothing() -> None:
    r = strain(truck_event())
    same = cond.compensate_temperature(r, temperatures([72.0] * 10))
    assert same.samples_ue == pytest.approx(r.samples_ue)


def test_a_warming_channel_takes_the_thermal_strain_back_out() -> None:
    # Forty degrees of warming is 260 microstrain of free expansion.
    ramp = [72.0 + 40.0 * i / 9.0 for i in range(10)]
    flat = strain([0.0] * 200)
    corrected = cond.compensate_temperature(flat, temperatures(ramp))
    assert corrected.samples_ue[0] > 0.0
    assert corrected.samples_ue[-1] < 0.0
    assert corrected.range_ue == pytest.approx(260.0, rel=0.05)


def test_compensation_is_referenced_to_the_mean_not_to_zero() -> None:
    hot = cond.compensate_temperature(strain([0.0] * 100), temperatures([110.0] * 10))
    cold = cond.compensate_temperature(strain([0.0] * 100), temperatures([20.0] * 10))
    assert hot.samples_ue == pytest.approx(cold.samples_ue)


def test_a_negative_expansion_coefficient_is_refused() -> None:
    with pytest.raises(RecordError, match="is negative"):
        cond.compensate_temperature(strain([0.0] * 50), temperatures([70.0] * 10), -1e-6)


def test_the_temperature_record_reports_its_swing() -> None:
    t = temperatures([60.0, 64.0, 70.0, 78.0, 84.0, 88.0, 90.0, 91.0])
    assert t.swing_degf == pytest.approx(31.0)
    assert t.mean_degf == pytest.approx(sum(t.samples_degf) / 8.0)


def test_reading_the_temperature_by_fraction_hits_both_ends() -> None:
    t = temperatures([60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0, 95.0])
    assert t.at_fraction(0.0) == pytest.approx(60.0)
    assert t.at_fraction(1.0) == pytest.approx(95.0)


def test_a_fraction_outside_the_record_clamps() -> None:
    t = temperatures([60.0] * 8)
    assert t.at_fraction(-3.0) == pytest.approx(60.0)
    assert t.at_fraction(9.0) == pytest.approx(60.0)


def test_a_temperature_record_needs_a_channel_id() -> None:
    with pytest.raises(RecordError, match="needs a channel id"):
        TemperatureRecord(
            channel_id="", started_at=START, sample_rate_hz=1.0, samples_degf=(70.0,) * 8
        )


def test_a_temperature_record_needs_a_sample_rate() -> None:
    with pytest.raises(RecordError, match="is not a rate"):
        TemperatureRecord(
            channel_id="T", started_at=START, sample_rate_hz=0.0, samples_degf=(70.0,) * 8
        )


def test_a_short_temperature_record_is_refused() -> None:
    with pytest.raises(RecordError, match="too few to compensate"):
        temperatures([70.0, 71.0])


def test_a_temperature_sample_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(RecordError, match="sample 3 is not a number"):
        temperatures([70.0, 71.0, 72.0, float("nan"), 74.0, 75.0, 76.0, 77.0])


def afternoon_temperatures() -> TemperatureRecord:
    """Warms through the record and then falls back, so the profile is a curve
    that a straight drift fit cannot absorb."""
    return temperatures([70.0, 76.0, 83.0, 89.0, 92.0, 90.0, 84.0, 78.0, 74.0, 72.0])


def test_the_whole_chain_leaves_a_centred_record_with_the_event_intact() -> None:
    event = truck_event(count=600, peak_ue=150.0)
    weather = afternoon_temperatures()
    reference_degf = weather.mean_degf
    raw = []
    for index, value in enumerate(event):
        fraction = index / (len(event) - 1)
        thermal = 6.5e-6 * (weather.at_fraction(fraction) - reference_degf) * 1e6
        raw.append(value + thermal + 0.6 * index / RATE_HZ)
    out = cond.condition(strain(raw), weather)
    assert out.mean_ue == pytest.approx(0.0, abs=1e-9)
    assert out.range_ue == pytest.approx(150.0, rel=0.2)


def test_compensating_after_the_drift_fit_would_over_correct() -> None:
    # The thermal profile has a linear part. A drift fit run first swallows some
    # of it, and the later subtraction then takes that part out twice.
    event = truck_event(count=600, peak_ue=150.0)
    weather = afternoon_temperatures()
    reference_degf = weather.mean_degf
    raw = []
    for index, value in enumerate(event):
        fraction = index / (len(event) - 1)
        thermal = 6.5e-6 * (weather.at_fraction(fraction) - reference_degf) * 1e6
        raw.append(value + thermal + 0.6 * index / RATE_HZ)
    right_way = cond.condition(strain(raw), weather)
    wrong_way = cond.remove_offset(
        cond.compensate_temperature(cond.remove_drift(strain(raw)), weather)
    )
    assert abs(right_way.range_ue - 150.0) < abs(wrong_way.range_ue - 150.0)


def test_the_chain_runs_without_a_temperature_channel() -> None:
    out = cond.condition(strain(truck_event()))
    assert out.mean_ue == pytest.approx(0.0, abs=1e-9)


def test_the_chain_can_be_asked_for_the_end_window_fit() -> None:
    out = cond.condition(strain(truck_event(count=400)), use_end_windows=True)
    assert out.mean_ue == pytest.approx(0.0, abs=1e-9)
