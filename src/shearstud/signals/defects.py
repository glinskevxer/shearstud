"""Finding the parts of a record that are the instrument rather than the bridge.

Three things go wrong with a strain channel in the field and they need telling
apart, because the right response to each is different:

* a **dropout** is a stretch where the value stops moving at all. A lead has
  come off or the excitation has failed. The stretch carries no information and
  counting cycles across it invents a cycle at each end;
* a **rail hit** is a stretch pinned at the amplifier limit. There was real
  strain, and it was bigger than the range the channel was set up for, so the
  record understates it. This is the dangerous one, because the numbers look
  like data;
* a **spike** is one sample, or two, a long way from its neighbours with the
  record continuous either side. Electrical pickup. It is safe to repair.

Only spikes get repaired. A dropout or a rail hit is reported and the affected
window is excluded, because filling either one in means inventing the strain the
bridge saw and then counting fatigue cycles in it.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from shearstud.errors import RecordError
from shearstud.signals.series import StrainRecord

#: Sample to sample movement below this is not movement.
DEFAULT_FLAT_TOLERANCE_UE: Final[float] = 0.05

#: A flat stretch shorter than this is a quiet bridge, not a dead gauge.
DEFAULT_MIN_DROPOUT_SAMPLES: Final[int] = 25

#: How many robust deviations from the local trend makes a sample a spike.
DEFAULT_SPIKE_THRESHOLD: Final[float] = 8.0

#: Half width of the window the local trend is taken over.
DEFAULT_SPIKE_HALF_WINDOW: Final[int] = 4


@dataclass(frozen=True, slots=True)
class Interval:
    """A closed run of sample indices."""

    first: int
    last: int

    def __post_init__(self) -> None:
        if self.first < 0:
            raise RecordError(f"interval starts at {self.first}")
        if self.last < self.first:
            raise RecordError(f"interval from {self.first} to {self.last} runs backwards")

    @property
    def length(self) -> int:
        """How many samples the interval covers."""
        return self.last - self.first + 1

    def overlaps(self, other: Interval) -> bool:
        """True when the two share at least one sample."""
        return self.first <= other.last and other.first <= self.last

    def seconds(self, record: StrainRecord) -> float:
        """How long the interval lasted on a given record."""
        return self.length * record.interval_s


def find_dropouts(
    record: StrainRecord,
    flat_tolerance_ue: float = DEFAULT_FLAT_TOLERANCE_UE,
    min_samples: int = DEFAULT_MIN_DROPOUT_SAMPLES,
) -> list[Interval]:
    """Stretches where the signal stopped moving."""
    if flat_tolerance_ue < 0.0:
        raise RecordError(f"{record.gauge_id}: flat tolerance {flat_tolerance_ue} is negative")
    if min_samples < 2:
        raise RecordError(f"{record.gauge_id}: a dropout needs at least two samples")
    out: list[Interval] = []
    run_start = 0
    for index in range(1, record.sample_count):
        moved = abs(record.samples_ue[index] - record.samples_ue[index - 1]) > flat_tolerance_ue
        if moved:
            if index - run_start >= min_samples:
                out.append(Interval(run_start, index - 1))
            run_start = index
    if record.sample_count - run_start >= min_samples:
        out.append(Interval(run_start, record.sample_count - 1))
    return out


def find_rail_hits(record: StrainRecord, limit_ue: float, min_samples: int = 2) -> list[Interval]:
    """Stretches pinned at or beyond the channel's range."""
    if limit_ue <= 0.0:
        raise RecordError(f"{record.gauge_id}: channel limit {limit_ue} is not a limit")
    if min_samples < 1:
        raise RecordError(f"{record.gauge_id}: a rail hit needs at least one sample")
    out: list[Interval] = []
    run_start: int | None = None
    for index, value in enumerate(record.samples_ue):
        pinned = abs(value) >= limit_ue
        if pinned and run_start is None:
            run_start = index
        elif not pinned and run_start is not None:
            if index - run_start >= min_samples:
                out.append(Interval(run_start, index - 1))
            run_start = None
    if run_start is not None and record.sample_count - run_start >= min_samples:
        out.append(Interval(run_start, record.sample_count - 1))
    return out


def _local_median(samples: Sequence[float], index: int, half_window: int) -> float:
    low = max(0, index - half_window)
    high = min(len(samples), index + half_window + 1)
    neighbours = [samples[i] for i in range(low, high) if i != index]
    return statistics.median(neighbours)


def find_spikes(
    record: StrainRecord,
    threshold: float = DEFAULT_SPIKE_THRESHOLD,
    half_window: int = DEFAULT_SPIKE_HALF_WINDOW,
) -> list[int]:
    """Indices of samples that sit far off their own neighbourhood.

    The scale is the median absolute deviation of the whole record, which is
    robust to the spikes themselves. Using the standard deviation instead lets a
    big enough spike raise the scale until it stops being a spike.
    """
    if threshold <= 0.0:
        raise RecordError(f"{record.gauge_id}: spike threshold {threshold} is not a threshold")
    if half_window < 1:
        raise RecordError(f"{record.gauge_id}: spike window {half_window} is too narrow")
    samples = record.samples_ue
    centre = statistics.median(samples)
    deviations = sorted(abs(value - centre) for value in samples)
    scale = statistics.median(deviations)
    if scale <= 0.0:
        return []
    out: list[int] = []
    for index in range(record.sample_count):
        local = _local_median(samples, index, half_window)
        if abs(samples[index] - local) > threshold * scale:
            out.append(index)
    return out


def despike(
    record: StrainRecord,
    threshold: float = DEFAULT_SPIKE_THRESHOLD,
    half_window: int = DEFAULT_SPIKE_HALF_WINDOW,
) -> StrainRecord:
    """Replace each spike with the median of its neighbourhood."""
    spikes = find_spikes(record, threshold, half_window)
    if not spikes:
        return record
    repaired = list(record.samples_ue)
    for index in spikes:
        repaired[index] = _local_median(record.samples_ue, index, half_window)
    return record.with_samples(repaired)


def merge(intervals: Sequence[Interval], gap: int = 0) -> list[Interval]:
    """Join intervals that touch or are within ``gap`` samples of each other."""
    if gap < 0:
        raise RecordError(f"merge gap {gap} is negative")
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda i: (i.first, i.last))
    out = [ordered[0]]
    for candidate in ordered[1:]:
        last = out[-1]
        if candidate.first <= last.last + 1 + gap:
            out[-1] = Interval(last.first, max(last.last, candidate.last))
        else:
            out.append(candidate)
    return out


def covered_samples(intervals: Sequence[Interval]) -> int:
    """How many samples a set of intervals covers, overlaps counted once."""
    return sum(interval.length for interval in merge(intervals))
