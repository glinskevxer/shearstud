"""Gauge installations: what is on the structure, and what its readings mean.

A gauge is not just an id on a channel. It has a gauge factor that the logger
was configured with, an orientation that decides whether it reads the stress the
detail cares about, and a date it was bonded on, after which it drifts.

The two numbers that turn a channel into microstrain are the gauge factor and
the excitation, and both live here rather than in the record. A record carries
what the logger wrote; correcting it for a gauge factor the logger had wrong is
a job for this module, and it is a job that has been needed twice on this
inventory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

from shearstud.errors import InputError
from shearstud.signals.series import StrainRecord

#: Which way the grid runs relative to the girder axis.
ORIENTATION_LONGITUDINAL: Final[str] = "longitudinal"
ORIENTATION_TRANSVERSE: Final[str] = "transverse"
ORIENTATION_DIAGONAL: Final[str] = "diagonal"
ORIENTATIONS: Final[tuple[str, ...]] = (
    ORIENTATION_LONGITUDINAL,
    ORIENTATION_TRANSVERSE,
    ORIENTATION_DIAGONAL,
)

#: Nominal gauge factor for the foil gauges this agency buys.
NOMINAL_GAUGE_FACTOR: Final[float] = 2.10

#: A gauge factor this far off nominal is a different gauge, not a tolerance.
GAUGE_FACTOR_TOLERANCE: Final[float] = 0.25

#: How long a bonded foil gauge is trusted before the readings are treated as
#: indicative rather than quantitative.
SERVICE_LIFE_DAYS: Final[int] = 3 * 365


@dataclass(frozen=True, slots=True)
class GaugeInstall:
    """One gauge, as installed."""

    gauge_id: str
    detail_id: str
    orientation: str
    gauge_factor: float
    installed_on: date
    channel_limit_ue: float
    removed_on: date | None = None

    def __post_init__(self) -> None:
        if not self.gauge_id.strip():
            raise InputError("a gauge needs an id")
        if not self.detail_id.strip():
            raise InputError(f"{self.gauge_id}: a gauge needs a detail to watch")
        if self.orientation not in ORIENTATIONS:
            raise InputError(f"{self.gauge_id}: unknown orientation {self.orientation!r}")
        if abs(self.gauge_factor - NOMINAL_GAUGE_FACTOR) > GAUGE_FACTOR_TOLERANCE:
            raise InputError(
                f"{self.gauge_id}: gauge factor {self.gauge_factor} is more than "
                f"{GAUGE_FACTOR_TOLERANCE} off the nominal {NOMINAL_GAUGE_FACTOR}"
            )
        if self.channel_limit_ue <= 0.0:
            raise InputError(
                f"{self.gauge_id}: channel limit {self.channel_limit_ue} is not a limit"
            )
        if self.removed_on is not None and self.removed_on < self.installed_on:
            raise InputError(f"{self.gauge_id}: removed before it was installed")

    @property
    def reads_axial_stress(self) -> bool:
        """True when the grid is along the girder and reads bending stress.

        A transverse gauge on a flange reads Poisson strain and a distortion
        effect, and neither belongs in a flexural fatigue count.
        """
        return self.orientation == ORIENTATION_LONGITUDINAL

    def is_live_on(self, when: date) -> bool:
        """Whether the gauge was installed and not yet removed on a date."""
        if when < self.installed_on:
            return False
        return self.removed_on is None or when <= self.removed_on

    def days_in_service_at(self, when: date) -> int:
        """How long the gauge had been bonded on a date."""
        if when < self.installed_on:
            raise InputError(f"{self.gauge_id}: {when} is before it was installed")
        end = when if self.removed_on is None else min(when, self.removed_on)
        return (end - self.installed_on).days

    def is_past_service_life(self, when: date) -> bool:
        """True once the readings are indicative rather than quantitative."""
        return self.days_in_service_at(when) > SERVICE_LIFE_DAYS

    def corrected(self, record: StrainRecord, logged_factor: float) -> StrainRecord:
        """Rescale a record the logger computed with the wrong gauge factor.

        Strain reads inversely with the gauge factor, so a logger set two
        percent high produced readings two percent low.
        """
        if logged_factor <= 0.0:
            raise InputError(
                f"{self.gauge_id}: logged gauge factor {logged_factor} is not a factor"
            )
        ratio = logged_factor / self.gauge_factor
        if ratio == 1.0:
            return record
        return record.with_samples([value * ratio for value in record.samples_ue])


def live_on(installs: list[GaugeInstall], when: date) -> list[GaugeInstall]:
    """Gauges that were on the structure on a date, in id order."""
    return sorted((g for g in installs if g.is_live_on(when)), key=lambda g: g.gauge_id)


def for_detail(installs: list[GaugeInstall], detail_id: str) -> list[GaugeInstall]:
    """Every gauge watching one detail."""
    return [g for g in installs if g.detail_id == detail_id]


def axial_only(installs: list[GaugeInstall]) -> list[GaugeInstall]:
    """Only the gauges whose readings belong in a flexural fatigue count."""
    return [g for g in installs if g.reads_axial_stress]
