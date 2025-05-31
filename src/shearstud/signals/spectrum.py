"""Binning a cycle count into a histogram, which is how it gets stored.

A week of traffic on a busy structure is a few hundred thousand cycles, and
keeping every one of them is neither useful nor affordable. The histogram is
what goes in the book of record, and everything downstream reads it rather than
the raw list.

Binning loses information and the loss is not symmetric. Damage goes as the cube
of range, so a bin reported at its midpoint understates the damage from the
cycles in its upper half by more than it overstates the ones in its lower half.
This module reports the bin's own cube weighted representative range rather than
its midpoint, which removes the bias at the cost of storing one more number per
bin. On a five microstrain bin the difference is under a percent; on the wide
bins an old logger wrote, it is worth ten.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from shearstud.errors import RecordError
from shearstud.signals.rainflow import Cycle

#: Bin width the loggers on this inventory are configured for.
DEFAULT_BIN_WIDTH_UE = 5.0

#: Damage exponent used when collapsing a bin to one range.
DAMAGE_EXPONENT = 3.0


@dataclass(frozen=True, slots=True)
class SpectrumBin:
    """One bin of a cycle histogram."""

    low_ue: float
    width_ue: float
    count: float
    representative_ue: float

    def __post_init__(self) -> None:
        if self.width_ue <= 0.0:
            raise RecordError(f"bin width {self.width_ue} is not a width")
        if self.low_ue < 0.0:
            raise RecordError(f"bin starts at {self.low_ue}, below zero range")
        if self.count < 0.0:
            raise RecordError(f"bin count {self.count} is negative")
        if not self.low_ue <= self.representative_ue <= self.high_ue:
            raise RecordError(
                f"representative range {self.representative_ue} is outside "
                f"{self.low_ue} to {self.high_ue}"
            )

    @property
    def high_ue(self) -> float:
        """Upper edge of the bin, exclusive."""
        return self.low_ue + self.width_ue

    @property
    def midpoint_ue(self) -> float:
        """Centre of the bin, kept for comparison against the representative."""
        return self.low_ue + self.width_ue / 2.0


@dataclass(frozen=True, slots=True)
class Spectrum:
    """A cycle histogram, in ascending bins with no gaps."""

    gauge_id: str
    bin_width_ue: float
    bins: tuple[SpectrumBin, ...]

    def __post_init__(self) -> None:
        if not self.gauge_id.strip():
            raise RecordError("a spectrum needs a gauge id")
        if self.bin_width_ue <= 0.0:
            raise RecordError(f"{self.gauge_id}: bin width {self.bin_width_ue} is not a width")
        for earlier, later in zip(self.bins, self.bins[1:], strict=False):
            if later.low_ue <= earlier.low_ue:
                raise RecordError(f"{self.gauge_id}: bins are not in ascending order")

    def __len__(self) -> int:
        return len(self.bins)

    @property
    def total_count(self) -> float:
        """How many cycles the spectrum holds."""
        return sum(b.count for b in self.bins)

    @property
    def largest_range_ue(self) -> float:
        """Representative range of the highest occupied bin."""
        occupied = [b for b in self.bins if b.count > 0.0]
        if not occupied:
            return 0.0
        return max(b.representative_ue for b in occupied)

    def above(self, threshold_ue: float) -> float:
        """Cycles whose representative range is at or above a threshold.

        A cycle below the constant amplitude fatigue limit does no damage in an
        infinite life check, and this is what counts the ones that do.
        """
        return sum(b.count for b in self.bins if b.representative_ue >= threshold_ue)

    def truncated(self, threshold_ue: float) -> Spectrum:
        """The same spectrum with the bins below a threshold dropped."""
        if threshold_ue < 0.0:
            raise RecordError(f"{self.gauge_id}: threshold {threshold_ue} is negative")
        kept = tuple(b for b in self.bins if b.representative_ue >= threshold_ue)
        return Spectrum(self.gauge_id, self.bin_width_ue, kept)

    def equivalent_range_ue(self, exponent: float = DAMAGE_EXPONENT) -> float:
        """One range that would do the same damage as the whole spectrum."""
        if exponent <= 0.0:
            raise RecordError(f"{self.gauge_id}: exponent {exponent} is not positive")
        total = self.total_count
        if total <= 0.0:
            return 0.0
        weighted = sum(b.count * math.pow(b.representative_ue, exponent) for b in self.bins)
        return math.pow(weighted / total, 1.0 / exponent)

    def scaled_count(self, factor: float) -> Spectrum:
        """Every count multiplied, for extrapolating a sample to a year."""
        if factor < 0.0:
            raise RecordError(f"{self.gauge_id}: scale factor {factor} is negative")
        bins = tuple(
            SpectrumBin(b.low_ue, b.width_ue, b.count * factor, b.representative_ue)
            for b in self.bins
        )
        return Spectrum(self.gauge_id, self.bin_width_ue, bins)

    def merged_with(self, other: Spectrum) -> Spectrum:
        """Add another spectrum's counts to this one.

        Both have to share a bin width. Adding spectra binned differently is a
        real request and this is not the function for it: rebin one first, so
        the loss of resolution is visible where it happens.
        """
        if other.bin_width_ue != self.bin_width_ue:
            raise RecordError(
                f"{self.gauge_id}: cannot merge a {other.bin_width_ue} bin spectrum "
                f"into a {self.bin_width_ue} one"
            )
        merged: dict[int, tuple[float, float]] = {}
        for source in (self, other):
            for b in source.bins:
                key = int(round(b.low_ue / self.bin_width_ue))
                count, weighted = merged.get(key, (0.0, 0.0))
                merged[key] = (
                    count + b.count,
                    weighted + b.count * math.pow(b.representative_ue, DAMAGE_EXPONENT),
                )
        bins = []
        for key in sorted(merged):
            count, weighted = merged[key]
            low_ue = key * self.bin_width_ue
            if count > 0.0:
                representative = math.pow(weighted / count, 1.0 / DAMAGE_EXPONENT)
            else:
                representative = low_ue + self.bin_width_ue / 2.0
            bins.append(
                SpectrumBin(
                    low_ue,
                    self.bin_width_ue,
                    count,
                    _into_bin(representative, low_ue, self.bin_width_ue),
                )
            )
        return Spectrum(self.gauge_id, self.bin_width_ue, tuple(bins))


def _into_bin(value_ue: float, low_ue: float, width_ue: float) -> float:
    """Pull a representative range back inside its own bin.

    A cube weighted mean of values that all sit at one edge of a bin lands on
    that edge, and in floating point it lands a few parts in ten to the sixteen
    outside it. Clamping is not a correction, it is a rounding repair.
    """
    return min(max(value_ue, low_ue), low_ue + width_ue)


def build(
    gauge_id: str,
    cycles: Sequence[Cycle],
    bin_width_ue: float = DEFAULT_BIN_WIDTH_UE,
    exponent: float = DAMAGE_EXPONENT,
) -> Spectrum:
    """Bin a cycle count, keeping each bin's cube weighted representative."""
    if bin_width_ue <= 0.0:
        raise RecordError(f"{gauge_id}: bin width {bin_width_ue} is not a width")
    if exponent <= 0.0:
        raise RecordError(f"{gauge_id}: exponent {exponent} is not positive")
    tallies: dict[int, tuple[float, float]] = {}
    for cycle in cycles:
        key = int(cycle.range_ue // bin_width_ue)
        count, weighted = tallies.get(key, (0.0, 0.0))
        tallies[key] = (
            count + cycle.count,
            weighted + cycle.count * math.pow(cycle.range_ue, exponent),
        )
    bins = []
    for key in sorted(tallies):
        count, weighted = tallies[key]
        low_ue = key * bin_width_ue
        representative = math.pow(weighted / count, 1.0 / exponent) if count > 0.0 else low_ue
        clamped = _into_bin(representative, low_ue, bin_width_ue)
        bins.append(SpectrumBin(low_ue, bin_width_ue, count, clamped))
    return Spectrum(gauge_id, bin_width_ue, tuple(bins))
