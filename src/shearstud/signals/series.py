"""Strain records: a gauge, a start time, a sample rate and a run of samples.

The data logger writes a value every sample interval whether or not the gauge is
telling the truth, so a record has no gaps in it and never carries a missing
value. Bad stretches are found later, by looking at the numbers, and are
reported as intervals rather than punched into the samples. That keeps every
arithmetic routine in this package free of missing value handling, which is
worth more than it sounds: a mean that silently skips a hundred samples is a
mean nobody can reproduce.

Records are immutable. Every conditioning step returns a new record and says in
its name what it did, so a record that has been through the pipeline can be
compared against the one that came off the logger.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from shearstud.errors import RecordError

#: Slowest logger this inventory has ever used. Anything below is a
#: misconfigured channel rather than a slow one.
MIN_SAMPLE_RATE_HZ: Final[float] = 1.0

#: Fastest. Above this the file is a vibration study and not a strain record.
MAX_SAMPLE_RATE_HZ: Final[float] = 2000.0

#: A record shorter than this cannot carry a truck event and is not worth
#: counting cycles in.
MIN_SAMPLES: Final[int] = 8


@dataclass(frozen=True, slots=True)
class StrainRecord:
    """One channel of microstrain against time."""

    gauge_id: str
    started_at: datetime
    sample_rate_hz: float
    samples_ue: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.gauge_id.strip():
            raise RecordError("a strain record needs a gauge id")
        if not MIN_SAMPLE_RATE_HZ <= self.sample_rate_hz <= MAX_SAMPLE_RATE_HZ:
            raise RecordError(
                f"{self.gauge_id}: sample rate {self.sample_rate_hz} Hz is outside "
                f"{MIN_SAMPLE_RATE_HZ} to {MAX_SAMPLE_RATE_HZ}"
            )
        if len(self.samples_ue) < MIN_SAMPLES:
            raise RecordError(
                f"{self.gauge_id}: {len(self.samples_ue)} samples is shorter than the "
                f"{MIN_SAMPLES} a record needs"
            )
        for index, value in enumerate(self.samples_ue):
            if not math.isfinite(value):
                raise RecordError(f"{self.gauge_id}: sample {index} is not a number")

    def __len__(self) -> int:
        return len(self.samples_ue)

    @property
    def sample_count(self) -> int:
        """How many samples the record holds."""
        return len(self.samples_ue)

    @property
    def interval_s(self) -> float:
        """Seconds between samples."""
        return 1.0 / self.sample_rate_hz

    @property
    def duration_s(self) -> float:
        """Time from the first sample to the last one."""
        return (self.sample_count - 1) * self.interval_s

    @property
    def ended_at(self) -> datetime:
        """Timestamp of the last sample."""
        return self.started_at + timedelta(seconds=self.duration_s)

    def time_of(self, index: int) -> float:
        """Seconds from the start of the record to a sample."""
        if not 0 <= index < self.sample_count:
            raise RecordError(f"{self.gauge_id}: no sample {index} in {self.sample_count}")
        return index * self.interval_s

    def timestamp_of(self, index: int) -> datetime:
        """Wall clock time of a sample."""
        return self.started_at + timedelta(seconds=self.time_of(index))

    def index_at(self, seconds: float) -> int:
        """Nearest sample to a time offset, clamped to the record."""
        raw = round(seconds * self.sample_rate_hz)
        return max(0, min(self.sample_count - 1, int(raw)))

    @property
    def mean_ue(self) -> float:
        """Arithmetic mean of every sample."""
        return sum(self.samples_ue) / self.sample_count

    @property
    def peak_ue(self) -> float:
        """Largest sample."""
        return max(self.samples_ue)

    @property
    def trough_ue(self) -> float:
        """Smallest sample."""
        return min(self.samples_ue)

    @property
    def range_ue(self) -> float:
        """Peak to trough over the whole record."""
        return self.peak_ue - self.trough_ue

    @property
    def rms_ue(self) -> float:
        """Root mean square about zero, not about the mean."""
        total = sum(value * value for value in self.samples_ue)
        return math.sqrt(total / self.sample_count)

    def standard_deviation_ue(self) -> float:
        """Sample standard deviation about the record's own mean."""
        mean = self.mean_ue
        total = sum((value - mean) ** 2 for value in self.samples_ue)
        return math.sqrt(total / (self.sample_count - 1))

    def with_samples(self, samples_ue: Sequence[float]) -> StrainRecord:
        """A copy carrying different samples, everything else the same."""
        return StrainRecord(
            gauge_id=self.gauge_id,
            started_at=self.started_at,
            sample_rate_hz=self.sample_rate_hz,
            samples_ue=tuple(samples_ue),
        )

    def shifted_by(self, offset_ue: float) -> StrainRecord:
        """Every sample moved by a constant, for a baseline correction."""
        return self.with_samples([value + offset_ue for value in self.samples_ue])

    def window(self, start_s: float, end_s: float) -> StrainRecord:
        """A slice of the record, timestamped from where the slice starts."""
        if end_s <= start_s:
            raise RecordError(f"{self.gauge_id}: window from {start_s} to {end_s} has no length")
        first = self.index_at(start_s)
        last = self.index_at(end_s)
        samples = self.samples_ue[first : last + 1]
        if len(samples) < MIN_SAMPLES:
            raise RecordError(
                f"{self.gauge_id}: window from {start_s} to {end_s} holds {len(samples)} samples"
            )
        return StrainRecord(
            gauge_id=self.gauge_id,
            started_at=self.timestamp_of(first),
            sample_rate_hz=self.sample_rate_hz,
            samples_ue=samples,
        )

    def decimated(self, factor: int) -> StrainRecord:
        """Keep every nth sample, dropping the rate to match.

        No anti alias filter is applied and none is wanted. This is used to
        thin a long record for plotting and for a first pass at cycle counting,
        and both of those want the samples that were actually recorded.
        """
        if factor < 1:
            raise RecordError(f"{self.gauge_id}: decimation factor {factor} is not a factor")
        if factor == 1:
            return self
        return StrainRecord(
            gauge_id=self.gauge_id,
            started_at=self.started_at,
            sample_rate_hz=self.sample_rate_hz / factor,
            samples_ue=self.samples_ue[::factor],
        )
