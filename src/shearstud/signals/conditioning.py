"""Getting the load out of a strain record and the rest of it out of the way.

A bonded foil gauge on a girder reads four things at once: the strain the traffic
put there, the strain the sun put there, the slow wander of the amplifier, and
noise. Only the first one counts cycles. The three steps here strip the other
three, in this order and for this reason:

1. **temperature** comes off first, because it is a measured subtraction rather
   than a fit. The paired channel says what the thermal strain was, so removing
   it costs nothing and cannot be biased by anything else in the record;
2. **drift** comes off second, fitted to what is left. Fitting it first means
   the fitted line absorbs part of the thermal ramp, and the later temperature
   subtraction then removes that part a second time;
3. **offset** comes off last, because after the first two the record is
   stationary and the mean is a meaningful zero.

The order is only obvious in this direction because the temperature step is
measured. A gauge with no companion channel has to fit its temperature
coefficient instead, and then the drift genuinely does have to come off first
or it leaks into that fit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from shearstud.errors import RecordError
from shearstud.signals.series import MIN_SAMPLES, StrainRecord
from shearstud.units import STEEL_ALPHA_PER_DEGF, thermal_strain_ue

#: Default length of the quiet window at each end of a record used by the end
#: point drift fit. Long enough to average out noise, short enough that a truck
#: at the very start of the record does not swallow it.
DEFAULT_END_WINDOW_S: Final[float] = 2.0


@dataclass(frozen=True, slots=True)
class TemperatureRecord:
    """A temperature channel logged alongside a strain channel."""

    channel_id: str
    started_at: datetime
    sample_rate_hz: float
    samples_degf: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.channel_id.strip():
            raise RecordError("a temperature record needs a channel id")
        if self.sample_rate_hz <= 0.0:
            raise RecordError(f"{self.channel_id}: sample rate {self.sample_rate_hz} is not a rate")
        if len(self.samples_degf) < MIN_SAMPLES:
            raise RecordError(
                f"{self.channel_id}: {len(self.samples_degf)} samples is too few to compensate with"
            )
        for index, value in enumerate(self.samples_degf):
            if not math.isfinite(value):
                raise RecordError(f"{self.channel_id}: sample {index} is not a number")

    @property
    def mean_degf(self) -> float:
        """Mean temperature over the record."""
        return sum(self.samples_degf) / len(self.samples_degf)

    @property
    def swing_degf(self) -> float:
        """How far the temperature moved over the record."""
        return max(self.samples_degf) - min(self.samples_degf)

    def at_fraction(self, fraction: float) -> float:
        """Temperature a given way through the record.

        The temperature channel is usually logged far slower than the strain
        channel, so the two are lined up by position in the record rather than
        by sample index.
        """
        clamped = min(max(fraction, 0.0), 1.0)
        index = int(round(clamped * (len(self.samples_degf) - 1)))
        return self.samples_degf[index]


def remove_offset(record: StrainRecord) -> StrainRecord:
    """Subtract the record's own mean, putting its zero where it belongs."""
    return record.shifted_by(-record.mean_ue)


def fit_drift(record: StrainRecord) -> tuple[float, float]:
    """Least squares straight line through the record, as slope and intercept.

    Slope is microstrain per second. Returned rather than applied so that the
    quality report can look at how much drift there was without recomputing it.
    """
    n = record.sample_count
    mean_x = (n - 1) / 2.0
    mean_y = record.mean_ue
    covariance = 0.0
    variance = 0.0
    for index, value in enumerate(record.samples_ue):
        dx = index - mean_x
        covariance += dx * (value - mean_y)
        variance += dx * dx
    slope_per_sample = covariance / variance if variance > 0.0 else 0.0
    intercept = mean_y - slope_per_sample * mean_x
    return slope_per_sample * record.sample_rate_hz, intercept


def remove_drift(record: StrainRecord) -> StrainRecord:
    """Subtract the least squares straight line.

    This is the right choice when the record is long relative to the events in
    it, so that the events do not tilt the fit. A short record with one big
    truck in it wants :func:`remove_drift_by_ends` instead.
    """
    slope_per_s, intercept = fit_drift(record)
    slope_per_sample = slope_per_s / record.sample_rate_hz
    corrected = [
        value - (intercept + slope_per_sample * index)
        for index, value in enumerate(record.samples_ue)
    ]
    return record.with_samples(corrected)


def remove_drift_by_ends(
    record: StrainRecord, window_s: float = DEFAULT_END_WINDOW_S
) -> StrainRecord:
    """Subtract the line joining the quiet ends of the record.

    Both ends are assumed unloaded, which is how the logger is triggered: it
    keeps a lead in and a lead out either side of the event. A truck sitting in
    one of those windows is a bad trigger and shows up as a large residual.
    """
    if window_s <= 0.0:
        raise RecordError(f"{record.gauge_id}: end window {window_s} s is not a window")
    span = record.index_at(window_s)
    if span < 1 or span * 2 >= record.sample_count:
        raise RecordError(
            f"{record.gauge_id}: a {window_s} s window does not fit in a "
            f"{record.duration_s:.2f} s record"
        )
    head = sum(record.samples_ue[: span + 1]) / (span + 1)
    tail = sum(record.samples_ue[-(span + 1) :]) / (span + 1)
    first_centre = span / 2.0
    last_centre = record.sample_count - 1 - span / 2.0
    slope = (tail - head) / (last_centre - first_centre)
    corrected = [
        value - (head + slope * (index - first_centre))
        for index, value in enumerate(record.samples_ue)
    ]
    return record.with_samples(corrected)


def compensate_temperature(
    record: StrainRecord,
    temperatures: TemperatureRecord,
    alpha_per_degf: float = STEEL_ALPHA_PER_DEGF,
) -> StrainRecord:
    """Subtract the free thermal strain implied by a paired temperature channel.

    The reference is the mean temperature over the record, so the compensation
    removes the change in temperature and not the absolute temperature. A gauge
    installed at eighty degrees and read at eighty degrees has nothing to
    compensate whatever the absolute number is.
    """
    if alpha_per_degf < 0.0:
        raise RecordError(f"{record.gauge_id}: expansion coefficient {alpha_per_degf} is negative")
    reference_degf = temperatures.mean_degf
    last = record.sample_count - 1
    corrected: list[float] = []
    for index, value in enumerate(record.samples_ue):
        fraction = index / last if last > 0 else 0.0
        delta_degf = temperatures.at_fraction(fraction) - reference_degf
        corrected.append(value - thermal_strain_ue(delta_degf, alpha_per_degf))
    return record.with_samples(corrected)


def condition(
    record: StrainRecord,
    temperatures: TemperatureRecord | None = None,
    *,
    use_end_windows: bool = False,
) -> StrainRecord:
    """The three steps in the order the module docstring argues for."""
    stage = record
    if temperatures is not None:
        stage = compensate_temperature(stage, temperatures)
    stage = remove_drift_by_ends(stage) if use_end_windows else remove_drift(stage)
    return remove_offset(stage)
