"""Truck events: where the hysteresis earns its keep."""

from __future__ import annotations

from datetime import datetime

import pytest

from shearstud.errors import RecordError
from shearstud.signals import events
from shearstud.signals.events import Event
from shearstud.signals.series import StrainRecord

pytestmark = pytest.mark.signals


def record(samples: list[float], rate_hz: float = 10.0) -> StrainRecord:
    return StrainRecord(
        gauge_id="G2-BF-MID",
        started_at=datetime(2025, 4, 8, 6, 0, 0),
        sample_rate_hz=rate_hz,
        samples_ue=tuple(samples),
    )


def truck(peak_ue: float, samples: int = 9) -> list[float]:
    """A triangular pass with the peak in the middle."""
    half = samples // 2
    up = [peak_ue * (step + 1) / (half + 1) for step in range(half)]
    return [*up, peak_ue, *reversed(up)]


QUIET = [0.0] * 12


def test_one_truck_gives_one_event() -> None:
    found = events.find(record([*QUIET, *truck(120.0), *QUIET]), trigger_ue=40.0)
    assert len(found) == 1


def test_two_trucks_with_a_gap_give_two_events() -> None:
    samples = [*QUIET, *truck(120.0), *QUIET, *truck(90.0), *QUIET]
    found = events.find(record(samples), trigger_ue=40.0)
    assert len(found) == 2


def test_the_peak_is_the_largest_sample_in_the_event() -> None:
    found = events.find(record([*QUIET, *truck(120.0), *QUIET]), trigger_ue=40.0)
    assert found[0].peak_ue == pytest.approx(120.0)


def test_the_peak_index_points_at_that_sample() -> None:
    samples = [*QUIET, *truck(120.0), *QUIET]
    found = events.find(record(samples), trigger_ue=40.0)
    assert samples[found[0].peak_index] == pytest.approx(120.0)


def test_the_events_come_back_in_the_order_they_happened() -> None:
    samples = [*QUIET, *truck(90.0), *QUIET, *truck(120.0), *QUIET]
    found = events.find(record(samples), trigger_ue=40.0)
    assert [event.peak_ue for event in found] == pytest.approx([90.0, 120.0])
    assert found[0].first < found[1].first


def test_a_signal_hovering_on_the_trigger_is_still_one_event() -> None:
    # This is the whole reason for the release fraction. With a single
    # threshold the dip back to 39 would end the event and start another.
    samples = [*QUIET, 45.0, 39.0, 47.0, 41.0, 120.0, 44.0, 38.0, 42.0, *QUIET]
    found = events.find(record(samples), trigger_ue=40.0)
    assert len(found) == 1


def test_the_same_signal_breaks_up_when_the_release_is_raised() -> None:
    samples = [*QUIET, 45.0, 39.0, 47.0, 41.0, 120.0, 44.0, 38.0, 42.0, *QUIET]
    found = events.find(record(samples), trigger_ue=40.0, release_frac=0.99, min_samples=1)
    assert len(found) > 1


def test_a_quiet_record_has_no_events() -> None:
    assert events.find(record(QUIET * 3), trigger_ue=40.0) == []


def test_a_blip_shorter_than_the_minimum_is_not_an_event() -> None:
    samples = [*QUIET, 200.0, 200.0, *QUIET]
    assert events.find(record(samples), trigger_ue=40.0) == []


def test_the_same_blip_counts_when_the_minimum_is_lowered() -> None:
    samples = [*QUIET, 200.0, 200.0, *QUIET]
    found = events.find(record(samples), trigger_ue=40.0, min_samples=2)
    assert len(found) == 1


def test_a_truck_still_on_the_bridge_at_the_end_is_kept() -> None:
    samples = [*QUIET, 50.0, 90.0, 130.0, 160.0, 180.0]
    found = events.find(record(samples), trigger_ue=40.0)
    assert len(found) == 1
    assert found[0].last == len(samples) - 1


def test_a_truck_arriving_in_the_last_sample_is_not_an_event() -> None:
    samples = [*QUIET, *QUIET, 50.0]
    assert events.find(record(samples), trigger_ue=40.0) == []


def test_a_trigger_at_zero_is_refused() -> None:
    with pytest.raises(RecordError, match="not a threshold"):
        events.find(record(QUIET * 3), trigger_ue=0.0)


def test_a_release_fraction_at_one_is_refused() -> None:
    with pytest.raises(RecordError, match="outside zero to one"):
        events.find(record(QUIET * 3), trigger_ue=40.0, release_frac=1.0)


def test_a_minimum_of_zero_samples_is_refused() -> None:
    with pytest.raises(RecordError, match="at least one sample"):
        events.find(record(QUIET * 3), trigger_ue=40.0, min_samples=0)


def test_the_length_counts_both_ends() -> None:
    assert Event(first=10, last=14, peak_ue=100.0, peak_index=12).length == 5


def test_an_event_running_backwards_is_refused() -> None:
    with pytest.raises(RecordError, match="runs backwards"):
        Event(first=14, last=10, peak_ue=100.0, peak_index=12)


def test_an_event_starting_before_the_record_is_refused() -> None:
    with pytest.raises(RecordError, match="event starts at"):
        Event(first=-1, last=10, peak_ue=100.0, peak_index=0)


def test_a_peak_outside_the_event_is_refused() -> None:
    with pytest.raises(RecordError, match="outside the event"):
        Event(first=10, last=14, peak_ue=100.0, peak_index=20)


def test_the_duration_follows_the_sample_rate() -> None:
    event = Event(first=10, last=19, peak_ue=100.0, peak_index=12)
    assert event.seconds(record(QUIET * 3, rate_hz=10.0)) == pytest.approx(1.0)
    assert event.seconds(record(QUIET * 3, rate_hz=20.0)) == pytest.approx(0.5)


def test_the_speed_hint_is_in_the_right_neighbourhood() -> None:
    # Ten samples at 10 Hz is one second; a 60 foot span crossed in a second
    # is about 41 mph.
    event = Event(first=0, last=9, peak_ue=100.0, peak_index=4)
    speed = event.speed_hint_mph(record(QUIET * 3, rate_hz=10.0), span_ft=60.0)
    assert speed == pytest.approx(40.9, abs=0.1)


def test_a_slower_crossing_reads_slower() -> None:
    fast = Event(first=0, last=9, peak_ue=100.0, peak_index=4)
    slow = Event(first=0, last=29, peak_ue=100.0, peak_index=4)
    clock = record(QUIET * 3)
    assert slow.speed_hint_mph(clock, span_ft=60.0) < fast.speed_hint_mph(clock, span_ft=60.0)


def test_a_span_of_zero_has_no_speed() -> None:
    event = Event(first=0, last=9, peak_ue=100.0, peak_index=4)
    with pytest.raises(RecordError, match="not a span"):
        event.speed_hint_mph(record(QUIET * 3), span_ft=0.0)


def test_cutting_keeps_the_event_and_the_margin() -> None:
    samples = [*QUIET, *QUIET, *truck(120.0), *QUIET, *QUIET]
    whole = record(samples)
    event = events.find(whole, trigger_ue=40.0)[0]
    piece = events.cut(whole, event, margin=5)
    assert piece.peak_ue == pytest.approx(120.0)
    assert piece.sample_count == event.length + 10


def test_a_cut_is_timestamped_from_where_it_starts() -> None:
    samples = [*QUIET, *QUIET, *truck(120.0), *QUIET, *QUIET]
    whole = record(samples)
    event = events.find(whole, trigger_ue=40.0)[0]
    piece = events.cut(whole, event, margin=5)
    assert piece.started_at == whole.timestamp_of(event.first - 5)


def test_a_cut_at_the_start_of_the_record_is_clipped_not_padded() -> None:
    samples = [50.0, 90.0, 130.0, 160.0, 90.0, 0.0, *QUIET]
    whole = record(samples)
    event = events.find(whole, trigger_ue=40.0)[0]
    piece = events.cut(whole, event, margin=20)
    assert piece.sample_count == whole.sample_count
    assert piece.started_at == whole.started_at


def test_a_negative_margin_is_refused() -> None:
    samples = [*QUIET, *truck(120.0), *QUIET]
    whole = record(samples)
    event = events.find(whole, trigger_ue=40.0)[0]
    with pytest.raises(RecordError, match="is negative"):
        events.cut(whole, event, margin=-1)


def test_the_cut_carries_the_gauge_and_the_rate_across() -> None:
    samples = [*QUIET, *truck(120.0), *QUIET]
    whole = record(samples)
    piece = events.cut(whole, events.find(whole, trigger_ue=40.0)[0])
    assert piece.gauge_id == whole.gauge_id
    assert piece.sample_rate_hz == whole.sample_rate_hz


def test_the_daily_rate_scales_a_short_record_up() -> None:
    samples = [*QUIET, *truck(120.0), *QUIET, *truck(90.0), *QUIET]
    whole = record(samples)
    found = events.find(whole, trigger_ue=40.0)
    assert events.daily_rate(whole, found) == pytest.approx(2 * 86400.0 / whole.duration_s)


def test_a_record_with_no_events_rates_at_zero() -> None:
    whole = record(QUIET * 3)
    assert events.daily_rate(whole, []) == 0.0


def test_the_heaviest_event_is_the_one_with_the_largest_peak() -> None:
    samples = [*QUIET, *truck(90.0), *QUIET, *truck(160.0), *QUIET, *truck(120.0), *QUIET]
    found = events.find(record(samples), trigger_ue=40.0)
    assert events.heaviest(found).peak_ue == pytest.approx(160.0)


def test_a_tie_on_the_peak_goes_to_the_earlier_event() -> None:
    first = Event(first=10, last=19, peak_ue=140.0, peak_index=14)
    second = Event(first=40, last=49, peak_ue=140.0, peak_index=44)
    assert events.heaviest([first, second]) is first
    assert events.heaviest([second, first]) is first


def test_asking_for_the_heaviest_of_nothing_is_refused() -> None:
    with pytest.raises(RecordError, match="no events"):
        events.heaviest([])


def test_filtering_keeps_the_events_that_reached_the_threshold() -> None:
    samples = [*QUIET, *truck(90.0), *QUIET, *truck(160.0), *QUIET]
    found = events.find(record(samples), trigger_ue=40.0)
    assert len(events.above(found, 100.0)) == 1
    assert len(events.above(found, 200.0)) == 0
    assert len(events.above(found, 10.0)) == 2


def test_the_threshold_is_inclusive() -> None:
    event = Event(first=10, last=19, peak_ue=140.0, peak_index=14)
    assert events.above([event], 140.0) == [event]
