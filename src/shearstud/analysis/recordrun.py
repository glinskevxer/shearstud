"""A raw logger file, taken all the way through to a spectrum in the book.

Until now a cycle count arrived from somewhere else and this package only read
it. That left the four modules that turn strain into a count wired to nothing
but their own tests, which is the state a module is in just before somebody
discovers it disagrees with the thing that actually feeds it.

The order of the steps is the whole content of this module and it is not
negotiable:

1. **defects first, on the raw record.** A dropout is a flat run at whatever the
   logger writes when the bridge is gone, and conditioning moves that value. A
   rail hit is a sample at the channel limit, and conditioning moves that too.
   Look for both while they are still where the logger put them.
2. **conditioning next**, and inside it temperature before drift, for the
   reason that module argues at length.
3. **counting last.** Rainflow on a conditioned record, binned into a spectrum.

Events come out alongside, and they are not on the path to the count. They are
what an engineer looks at when the count comes back wrong, and computing them
here means the count and the trucks behind it came from the same file.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from shearstud.errors import RecordError
from shearstud.signals import conditioning, defects, events, rainflow, spectrum
from shearstud.signals.events import Event
from shearstud.signals.series import StrainRecord
from shearstud.signals.spectrum import Spectrum
from shearstud.store.measurement import SpectrumQuality

#: Fraction of the conditioned record's peak that triggers an event.
DEFAULT_TRIGGER_FRAC: Final[float] = 0.35

#: Smallest trigger worth using, whatever the fraction works out to. A quiet
#: night on a quiet route has a peak of four microstrain and triggering at a
#: third of that finds four hundred events in the noise.
MIN_TRIGGER_UE: Final[float] = 15.0


@dataclass(frozen=True, slots=True)
class RecordRun:
    """What one logger file turned into, and what was wrong with it."""

    gauge_id: str
    raw: StrainRecord
    conditioned: StrainRecord
    quality: SpectrumQuality
    spectrum: Spectrum
    events: tuple[Event, ...]

    @property
    def sample_count(self) -> int:
        """How many samples the file carried."""
        return self.raw.sample_count

    @property
    def duration_s(self) -> float:
        """How long the record ran."""
        return self.raw.duration_s

    @property
    def events_per_day(self) -> float:
        """Crossings a day, extrapolated from however long the record ran."""
        return events.daily_rate(self.raw, list(self.events))

    @property
    def counted_cycles(self) -> float:
        """Loops the rainflow counter found."""
        return self.spectrum.total_count

    @property
    def cycles_per_event(self) -> float:
        """Loops per truck, which is the number a fatigue evaluation assumes.

        Comparing this against the assumed value is the cheapest check there is
        on whether the assumption holds for this structure, and on a short
        continuous span it frequently does not.
        """
        if not self.events:
            return 0.0
        return self.counted_cycles / len(self.events)


def read(path: Path | str, gauge_id: str, sample_rate_hz: float) -> StrainRecord:
    """One column of microstrain from a logger file.

    Two columns are accepted, a timestamp and a value, and the timestamp is
    read only for the first row. The sample rate is passed in rather than
    inferred from the timestamps because a logger that drops a sample leaves a
    gap the inference would read as a slower rate for the whole file.
    """
    source = Path(path)
    samples: list[float] = []
    started_at: datetime | None = None
    with source.open(encoding="utf-8", newline="") as handle:
        for line_number, row in enumerate(csv.reader(handle), start=1):
            # Blank when every cell is blank, not when the first one is. A
            # logger that writes the timestamp once an hour leaves it empty on
            # every other row, and those rows carry the strain.
            if not any(cell.strip() for cell in row):
                continue
            stamp = row[0].strip() if len(row) > 1 else ""
            if stamp and started_at is None:
                try:
                    started_at = datetime.fromisoformat(stamp)
                except ValueError:
                    if line_number > 1:
                        raise RecordError(
                            f"{source.name} line {line_number}: {stamp!r} is not a timestamp"
                        ) from None
            try:
                samples.append(float(row[-1]))
            except ValueError:
                if line_number == 1:
                    continue
                raise RecordError(
                    f"{source.name} line {line_number}: {row[-1]!r} is not a strain reading"
                ) from None
    if not samples:
        raise RecordError(f"{source.name} holds no strain readings")
    return StrainRecord(
        gauge_id=gauge_id,
        started_at=started_at or datetime(1970, 1, 1),
        sample_rate_hz=sample_rate_hz,
        samples_ue=tuple(samples),
    )


def quality_of(record: StrainRecord, limit_ue: float) -> SpectrumQuality:
    """How much of a raw record was not usable, before anything touched it."""
    dropouts = defects.find_dropouts(record)
    railed = defects.find_rail_hits(record, limit_ue)
    total = float(record.sample_count)
    return SpectrumQuality(
        dropout_frac=defects.covered_samples(dropouts) / total,
        railed_frac=defects.covered_samples(railed) / total,
    )


def trigger_for(record: StrainRecord, fraction: float = DEFAULT_TRIGGER_FRAC) -> float:
    """The event trigger to use on a conditioned record."""
    if not 0.0 < fraction < 1.0:
        raise RecordError(f"{record.gauge_id}: trigger fraction {fraction} is outside zero to one")
    return max(MIN_TRIGGER_UE, record.peak_ue * fraction)


def run(
    path: Path | str,
    gauge_id: str,
    sample_rate_hz: float,
    limit_ue: float,
    *,
    bin_width_ue: float = 5.0,
    trigger_frac: float = DEFAULT_TRIGGER_FRAC,
) -> RecordRun:
    """Read a logger file and take it through to a spectrum."""
    raw = read(path, gauge_id, sample_rate_hz)
    quality = quality_of(raw, limit_ue)
    conditioned = conditioning.condition(defects.despike(raw))
    cycles = rainflow.count_cycles(list(conditioned.samples_ue))
    counted = spectrum.build(gauge_id, cycles, bin_width_ue)
    found = events.find(conditioned, trigger_for(conditioned, trigger_frac))
    return RecordRun(
        gauge_id=gauge_id,
        raw=raw,
        conditioned=conditioned,
        quality=quality,
        spectrum=counted,
        events=tuple(found),
    )
