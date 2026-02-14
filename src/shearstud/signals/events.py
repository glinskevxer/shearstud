"""Pulling individual truck events out of a continuous strain record.

A logger left running writes one long record. What a fatigue evaluation wants is
the cycle count, which does not need events at all; what an engineer wants when
the count comes back wrong is to look at the trucks, and that needs them.

An event is a stretch where the strain rises above a trigger and comes back
below a lower release. Two thresholds rather than one is the whole design: a
single threshold on a signal that hovers near it produces a hundred events out
of one truck, and the hysteresis between the two is what stops that. The release
is a fraction of the trigger rather than a separate number, so there is one
knob and it cannot be set inconsistently.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from shearstud.errors import RecordError
from shearstud.signals.series import StrainRecord

#: Fraction of the trigger at which an event is considered over.
RELEASE_FRAC: Final[float] = 0.4

#: Shortest an event may be, in samples. Below this it is a spike the defect
#: pass should have taken, not a vehicle.
MIN_EVENT_SAMPLES: Final[int] = 4

#: How much quiet record is kept either side of an event when it is cut out.
DEFAULT_MARGIN_SAMPLES: Final[int] = 10


@dataclass(frozen=True, slots=True)
class Event:
    """One vehicle crossing, as the record saw it."""

    first: int
    last: int
    peak_ue: float
    peak_index: int

    def __post_init__(self) -> None:
        if self.first < 0:
            raise RecordError(f"event starts at {self.first}")
        if self.last < self.first:
            raise RecordError(f"event from {self.first} to {self.last} runs backwards")
        if not self.first <= self.peak_index <= self.last:
            raise RecordError(f"the peak at {self.peak_index} is outside the event")

    @property
    def length(self) -> int:
        """How many samples the event covers."""
        return self.last - self.first + 1

    def seconds(self, record: StrainRecord) -> float:
        """How long the crossing took."""
        return self.length * record.interval_s

    def speed_hint_mph(self, record: StrainRecord, span_ft: float) -> float:
        """A rough crossing speed, for sanity rather than for enforcement.

        A vehicle is on the influence line for roughly the span plus its own
        length, and the length is not known here, so this reads low by however
        long the truck is. It is useful for telling a truck from a tractor and
        for nothing else.
        """
        if span_ft <= 0.0:
            raise RecordError(f"span {span_ft} is not a span")
        duration_s = self.seconds(record)
        if duration_s <= 0.0:
            raise RecordError("an event with no duration has no speed")
        return span_ft / duration_s * 3600.0 / 5280.0


def find(
    record: StrainRecord,
    trigger_ue: float,
    release_frac: float = RELEASE_FRAC,
    min_samples: int = MIN_EVENT_SAMPLES,
) -> list[Event]:
    """Every crossing in a record, in the order they happened."""
    if trigger_ue <= 0.0:
        raise RecordError(f"{record.gauge_id}: trigger {trigger_ue} is not a threshold")
    if not 0.0 < release_frac < 1.0:
        raise RecordError(
            f"{record.gauge_id}: release fraction {release_frac} is outside zero to one"
        )
    if min_samples < 1:
        raise RecordError(f"{record.gauge_id}: an event needs at least one sample")
    release_ue = trigger_ue * release_frac

    out: list[Event] = []
    start: int | None = None
    peak_ue = 0.0
    peak_index = 0
    for index, value in enumerate(record.samples_ue):
        if start is None:
            if value >= trigger_ue:
                start = index
                peak_ue = value
                peak_index = index
            continue
        if value > peak_ue:
            peak_ue = value
            peak_index = index
        if value < release_ue:
            if index - start >= min_samples:
                out.append(Event(start, index - 1, peak_ue, peak_index))
            start = None
    if start is not None and record.sample_count - start >= min_samples:
        out.append(Event(start, record.sample_count - 1, peak_ue, peak_index))
    return out


def cut(record: StrainRecord, event: Event, margin: int = DEFAULT_MARGIN_SAMPLES) -> StrainRecord:
    """The record around one event, with a margin of quiet either side."""
    if margin < 0:
        raise RecordError(f"{record.gauge_id}: margin {margin} is negative")
    first = max(0, event.first - margin)
    last = min(record.sample_count - 1, event.last + margin)
    samples = record.samples_ue[first : last + 1]
    return StrainRecord(
        gauge_id=record.gauge_id,
        started_at=record.timestamp_of(first),
        sample_rate_hz=record.sample_rate_hz,
        samples_ue=samples,
    )


def daily_rate(record: StrainRecord, events: list[Event]) -> float:
    """Events a day, from the length of the record they came out of."""
    duration_s = record.duration_s
    if duration_s <= 0.0:
        raise RecordError(f"{record.gauge_id}: a record with no duration has no rate")
    return len(events) * 86400.0 / duration_s


def heaviest(events: list[Event]) -> Event:
    """The event with the largest peak, ties broken by which came first."""
    if not events:
        raise RecordError("no events to choose between")
    return max(events, key=lambda event: (event.peak_ue, -event.first))


def above(events: list[Event], threshold_ue: float) -> list[Event]:
    """Events whose peak reached a threshold."""
    return [event for event in events if event.peak_ue >= threshold_ue]
