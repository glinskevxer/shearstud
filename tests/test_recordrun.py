"""A logger file taken through to a spectrum, and the order the steps run in."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from shearstud.analysis import recordrun as rec
from shearstud.errors import RecordError
from shearstud.signals.series import StrainRecord

pytestmark = pytest.mark.signals

RATE_HZ = 20.0
LIMIT_UE = 1500.0
PEAK_UE = 180.0


def truck(peak_ue: float = PEAK_UE, samples: int = 21) -> list[float]:
    """A triangular pass, long enough at 20 Hz to be a truck and not a spike."""
    half = samples // 2
    up = [peak_ue * (step + 1) / (half + 1) for step in range(half)]
    return [*up, peak_ue, *reversed(up)]


def history(trucks: int = 12, drift_per_sample_ue: float = 0.0) -> list[float]:
    """A quiet record with trucks in it, optionally drifting."""
    out: list[float] = []
    for index in range(trucks):
        out.extend([0.0] * 12)
        out.extend(truck(PEAK_UE * (0.6 + 0.4 * ((index % 5) / 4.0))))
    out.extend([0.0] * 12)
    return [value + drift_per_sample_ue * index for index, value in enumerate(out)]


def written(tmp_path: Path, samples: list[float], header: bool = True, stamp: bool = True) -> Path:
    path = tmp_path / "strain.csv"
    rows = ["timestamp,ue"] if header else []
    for index, value in enumerate(samples):
        when = "2026-04-01T06:00:00" if index == 0 and stamp else ""
        rows.append(f"{when},{value:.4f}" if stamp else f"{value:.4f}")
    path.write_text("\n".join(rows), encoding="utf-8")
    return path


def test_a_file_reads_into_a_record(tmp_path: Path) -> None:
    record = rec.read(written(tmp_path, history()), "G2-BF-01", RATE_HZ)
    assert isinstance(record, StrainRecord)
    assert record.gauge_id == "G2-BF-01"
    assert record.sample_rate_hz == RATE_HZ


def test_the_header_row_is_skipped(tmp_path: Path) -> None:
    samples = history()
    record = rec.read(written(tmp_path, samples), "G2-BF-01", RATE_HZ)
    assert record.sample_count == len(samples)


def test_a_single_column_file_reads(tmp_path: Path) -> None:
    samples = history()
    path = written(tmp_path, samples, header=False, stamp=False)
    assert rec.read(path, "G2-BF-01", RATE_HZ).sample_count == len(samples)


def test_the_first_timestamp_becomes_the_start(tmp_path: Path) -> None:
    record = rec.read(written(tmp_path, history()), "G2-BF-01", RATE_HZ)
    assert record.started_at == datetime(2026, 4, 1, 6, 0, 0)


def test_a_file_with_no_timestamps_starts_at_the_epoch(tmp_path: Path) -> None:
    path = written(tmp_path, history(), header=False, stamp=False)
    assert rec.read(path, "G2-BF-01", RATE_HZ).started_at == datetime(1970, 1, 1)


def test_blank_rows_are_skipped(tmp_path: Path) -> None:
    samples = history()
    path = written(tmp_path, samples)
    path.write_text(path.read_text(encoding="utf-8") + "\n,\n\n", encoding="utf-8")
    assert rec.read(path, "G2-BF-01", RATE_HZ).sample_count == len(samples)


def test_a_reading_that_is_not_a_number_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "strain.csv"
    path.write_text("timestamp,ue\n,1.0\n,over range\n", encoding="utf-8")
    with pytest.raises(RecordError, match="not a strain reading"):
        rec.read(path, "G2-BF-01", RATE_HZ)


def test_a_timestamp_that_is_not_a_timestamp_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "strain.csv"
    path.write_text("timestamp,ue\nlast tuesday,1.0\n", encoding="utf-8")
    with pytest.raises(RecordError, match="not a timestamp"):
        rec.read(path, "G2-BF-01", RATE_HZ)


def test_an_empty_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "strain.csv"
    path.write_text("timestamp,ue\n", encoding="utf-8")
    with pytest.raises(RecordError, match="holds no strain readings"):
        rec.read(path, "G2-BF-01", RATE_HZ)


def test_a_clean_record_is_wholly_usable(tmp_path: Path) -> None:
    result = rec.run(written(tmp_path, history()), "G2-BF-01", RATE_HZ, LIMIT_UE)
    assert result.quality.usable_frac == pytest.approx(1.0)
    assert result.quality.is_trustworthy


def test_a_railed_record_is_not_trustworthy(tmp_path: Path) -> None:
    samples = history()
    samples[40:60] = [LIMIT_UE] * 20
    result = rec.run(written(tmp_path, samples), "G2-BF-01", RATE_HZ, LIMIT_UE)
    assert result.quality.railed_frac > 0.0
    assert not result.quality.is_trustworthy


def test_a_record_with_a_long_dropout_is_not_trustworthy(tmp_path: Path) -> None:
    samples = history(trucks=4)
    samples[10:200] = [0.0] * 190
    result = rec.run(written(tmp_path, samples), "G2-BF-01", RATE_HZ, LIMIT_UE)
    assert result.quality.dropout_frac > 0.10
    assert not result.quality.is_trustworthy


def test_the_quality_is_read_off_the_raw_record(tmp_path: Path) -> None:
    # A rail hit is a sample at the channel limit. Conditioning moves it, so
    # looking after conditioning finds nothing at all.
    samples = history(drift_per_sample_ue=0.05)
    samples[40:60] = [LIMIT_UE] * 20
    result = rec.run(written(tmp_path, samples), "G2-BF-01", RATE_HZ, LIMIT_UE)
    assert result.quality.railed_frac > 0.0
    assert rec.quality_of(result.conditioned, LIMIT_UE).railed_frac == 0.0


def test_conditioning_takes_the_drift_out(tmp_path: Path) -> None:
    straight = rec.run(written(tmp_path, history()), "G2-BF-01", RATE_HZ, LIMIT_UE)
    drifting = rec.run(
        written(tmp_path, history(drift_per_sample_ue=0.08)), "G2-BF-01", RATE_HZ, LIMIT_UE
    )
    assert drifting.raw.peak_ue > straight.raw.peak_ue
    assert drifting.conditioned.peak_ue == pytest.approx(straight.conditioned.peak_ue, rel=0.05)


def test_the_drift_does_not_reach_the_cycle_count(tmp_path: Path) -> None:
    straight = rec.run(written(tmp_path, history()), "G2-BF-01", RATE_HZ, LIMIT_UE)
    drifting = rec.run(
        written(tmp_path, history(drift_per_sample_ue=0.08)), "G2-BF-01", RATE_HZ, LIMIT_UE
    )
    assert drifting.spectrum.largest_range_ue == pytest.approx(
        straight.spectrum.largest_range_ue, rel=0.1
    )


def test_the_trucks_come_back_as_events(tmp_path: Path) -> None:
    result = rec.run(written(tmp_path, history(trucks=12)), "G2-BF-01", RATE_HZ, LIMIT_UE)
    assert len(result.events) == 12


def test_the_events_are_in_the_order_they_happened(tmp_path: Path) -> None:
    result = rec.run(written(tmp_path, history()), "G2-BF-01", RATE_HZ, LIMIT_UE)
    firsts = [event.first for event in result.events]
    assert firsts == sorted(firsts)


def test_the_counter_finds_at_least_one_loop_per_truck(tmp_path: Path) -> None:
    result = rec.run(written(tmp_path, history(trucks=12)), "G2-BF-01", RATE_HZ, LIMIT_UE)
    assert result.cycles_per_event >= 1.0


def test_a_record_with_no_events_has_no_loops_per_event(tmp_path: Path) -> None:
    quiet = [0.0, 1.0] * 40
    result = rec.run(written(tmp_path, quiet), "G2-BF-01", RATE_HZ, LIMIT_UE)
    assert result.events == ()
    assert result.cycles_per_event == 0.0


def test_the_daily_rate_scales_the_record_up(tmp_path: Path) -> None:
    result = rec.run(written(tmp_path, history(trucks=12)), "G2-BF-01", RATE_HZ, LIMIT_UE)
    assert result.events_per_day == pytest.approx(12 * 86400.0 / result.duration_s)


def test_the_run_reports_what_it_read(tmp_path: Path) -> None:
    samples = history()
    result = rec.run(written(tmp_path, samples), "G2-BF-01", RATE_HZ, LIMIT_UE)
    assert result.sample_count == len(samples)
    assert result.duration_s == pytest.approx((len(samples) - 1) / RATE_HZ)


def test_the_spectrum_carries_the_gauge_id(tmp_path: Path) -> None:
    result = rec.run(written(tmp_path, history()), "G2-BF-01", RATE_HZ, LIMIT_UE)
    assert result.spectrum.gauge_id == "G2-BF-01"


def test_a_wider_bin_gives_fewer_bins(tmp_path: Path) -> None:
    path = written(tmp_path, history())
    narrow = rec.run(path, "G2-BF-01", RATE_HZ, LIMIT_UE, bin_width_ue=2.0)
    wide = rec.run(path, "G2-BF-01", RATE_HZ, LIMIT_UE, bin_width_ue=25.0)
    assert len(wide.spectrum) < len(narrow.spectrum)
    assert wide.counted_cycles == pytest.approx(narrow.counted_cycles)


def test_the_trigger_is_a_fraction_of_the_peak() -> None:
    record = StrainRecord(
        gauge_id="G2-BF-01",
        started_at=datetime(2026, 4, 1),
        sample_rate_hz=RATE_HZ,
        samples_ue=(0.0, 100.0, 200.0, 100.0, 0.0, 50.0, 0.0, 10.0),
    )
    assert rec.trigger_for(record, 0.5) == pytest.approx(100.0)


def test_the_trigger_never_falls_below_the_floor() -> None:
    # A quiet night has a peak of four microstrain, and a third of that finds
    # four hundred events in the noise.
    record = StrainRecord(
        gauge_id="G2-BF-01",
        started_at=datetime(2026, 4, 1),
        sample_rate_hz=RATE_HZ,
        samples_ue=(0.0, 1.0, 4.0, 1.0, 0.0, 2.0, 0.0, 1.0),
    )
    assert rec.trigger_for(record) == pytest.approx(rec.MIN_TRIGGER_UE)


def test_a_trigger_fraction_outside_zero_to_one_is_refused() -> None:
    record = StrainRecord(
        gauge_id="G2-BF-01",
        started_at=datetime(2026, 4, 1),
        sample_rate_hz=RATE_HZ,
        samples_ue=(0.0, 1.0, 4.0, 1.0, 0.0, 2.0, 0.0, 1.0),
    )
    with pytest.raises(RecordError, match="outside zero to one"):
        rec.trigger_for(record, 1.5)


def test_a_higher_trigger_finds_fewer_events(tmp_path: Path) -> None:
    path = written(tmp_path, history())
    low = rec.run(path, "G2-BF-01", RATE_HZ, LIMIT_UE, trigger_frac=0.2)
    high = rec.run(path, "G2-BF-01", RATE_HZ, LIMIT_UE, trigger_frac=0.95)
    assert len(high.events) <= len(low.events)
