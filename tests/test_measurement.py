"""Storing what was measured, and the raw samples that deliberately are not."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from shearstud.errors import StorageError
from shearstud.signals import spectrum as spec
from shearstud.signals.rainflow import Cycle
from shearstud.signals.spectrum import Spectrum
from shearstud.store import measurement as meas
from shearstud.store.measurement import CampaignRecord, SpectrumQuality
from shearstud.structure.gauge import ORIENTATION_LONGITUDINAL, ORIENTATION_TRANSVERSE, GaugeInstall

pytestmark = pytest.mark.store


def install(
    gauge_id: str = "G3-BF-01",
    orientation: str = ORIENTATION_LONGITUDINAL,
    removed: date | None = None,
) -> GaugeInstall:
    return GaugeInstall(
        gauge_id=gauge_id,
        detail_id="D07",
        orientation=orientation,
        gauge_factor=2.10,
        installed_on=date(2025, 3, 14),
        channel_limit_ue=1500.0,
        removed_on=removed,
    )


def campaign(campaign_id: str = "C-2025-04") -> CampaignRecord:
    return CampaignRecord(
        campaign_id=campaign_id,
        structure_number="18-SH-0473",
        started_on=date(2025, 4, 1),
        ended_on=date(2025, 4, 14),
        seasonal_factor=1.15,
        note="spring wheat haul",
    )


def spectrum(gauge_id: str = "G3-BF-01") -> Spectrum:
    cycles = [
        Cycle(range_ue=40.0, mean_ue=0.0, count=12000.0),
        Cycle(range_ue=120.0, mean_ue=0.0, count=400.0),
        Cycle(range_ue=260.0, mean_ue=0.0, count=9.0),
    ]
    return spec.build(gauge_id, cycles, 5.0)


def test_a_gauge_round_trips(seeded_book: Path) -> None:
    meas.save_gauge(seeded_book, install())
    loaded = meas.load_gauges(seeded_book)
    assert len(loaded) == 1
    assert loaded[0].gauge_id == "G3-BF-01"
    assert loaded[0].gauge_factor == pytest.approx(2.10)
    assert loaded[0].installed_on == date(2025, 3, 14)
    assert loaded[0].removed_on is None


def test_a_removed_gauge_keeps_its_removal_date(seeded_book: Path) -> None:
    meas.save_gauge(seeded_book, install(removed=date(2026, 2, 1)))
    assert meas.load_gauges(seeded_book)[0].removed_on == date(2026, 2, 1)


def test_saving_a_gauge_twice_replaces_it(seeded_book: Path) -> None:
    meas.save_gauge(seeded_book, install())
    meas.save_gauge(seeded_book, install(removed=date(2026, 2, 1)))
    loaded = meas.load_gauges(seeded_book)
    assert len(loaded) == 1
    assert loaded[0].removed_on == date(2026, 2, 1)


def test_gauges_can_be_narrowed_to_one_detail(seeded_book: Path) -> None:
    meas.save_gauge(seeded_book, install("a"))
    meas.save_gauge(seeded_book, install("b", orientation=ORIENTATION_TRANSVERSE))
    assert len(meas.load_gauges(seeded_book, "D07")) == 2
    assert meas.load_gauges(seeded_book, "nowhere") == []


def test_a_gauge_watching_a_detail_that_is_not_there_is_refused(seeded_book: Path) -> None:
    import sqlite3

    orphan = GaugeInstall(
        gauge_id="x",
        detail_id="does-not-exist",
        orientation=ORIENTATION_LONGITUDINAL,
        gauge_factor=2.10,
        installed_on=date(2025, 3, 14),
        channel_limit_ue=1500.0,
    )
    with pytest.raises(sqlite3.IntegrityError):
        meas.save_gauge(seeded_book, orphan)


def test_a_campaign_round_trips(seeded_book: Path) -> None:
    meas.save_campaign(seeded_book, campaign())
    loaded = meas.load_campaigns(seeded_book, "18-SH-0473")
    assert len(loaded) == 1
    assert loaded[0].campaign_id == "C-2025-04"
    assert loaded[0].seasonal_factor == pytest.approx(1.15)
    assert loaded[0].note == "spring wheat haul"


def test_a_campaign_reports_its_length_in_days() -> None:
    assert campaign().days == pytest.approx(14.0)


def test_a_one_day_campaign_is_one_day() -> None:
    one = CampaignRecord(
        campaign_id="c",
        structure_number="s",
        started_on=date(2025, 4, 1),
        ended_on=date(2025, 4, 1),
    )
    assert one.days == pytest.approx(1.0)


def test_a_campaign_that_ends_before_it_starts_is_refused() -> None:
    with pytest.raises(StorageError, match="ended before it started"):
        CampaignRecord(
            campaign_id="c",
            structure_number="s",
            started_on=date(2025, 4, 14),
            ended_on=date(2025, 4, 1),
        )


def test_a_campaign_needs_an_id() -> None:
    with pytest.raises(StorageError, match="needs an id"):
        CampaignRecord(
            campaign_id=" ",
            structure_number="s",
            started_on=date(2025, 4, 1),
            ended_on=date(2025, 4, 14),
        )


def test_campaigns_come_back_oldest_first(seeded_book: Path) -> None:
    later = CampaignRecord(
        campaign_id="C-2026-05",
        structure_number="18-SH-0473",
        started_on=date(2026, 5, 1),
        ended_on=date(2026, 5, 14),
    )
    meas.save_campaign(seeded_book, later)
    meas.save_campaign(seeded_book, campaign())
    assert [c.campaign_id for c in meas.load_campaigns(seeded_book, "18-SH-0473")] == [
        "C-2025-04",
        "C-2026-05",
    ]


def test_a_spectrum_round_trips(seeded_book: Path) -> None:
    meas.save_gauge(seeded_book, install())
    meas.save_campaign(seeded_book, campaign())
    original = spectrum()
    meas.save_spectrum(seeded_book, "C-2025-04", original)
    loaded = meas.load_spectrum(seeded_book, "C-2025-04", "G3-BF-01")
    assert len(loaded) == len(original)
    assert loaded.total_count == pytest.approx(original.total_count)
    assert loaded.bin_width_ue == pytest.approx(original.bin_width_ue)


def test_the_spectrum_damage_survives_the_round_trip(seeded_book: Path) -> None:
    meas.save_gauge(seeded_book, install())
    meas.save_campaign(seeded_book, campaign())
    original = spectrum()
    meas.save_spectrum(seeded_book, "C-2025-04", original)
    loaded = meas.load_spectrum(seeded_book, "C-2025-04", "G3-BF-01")
    assert loaded.equivalent_range_ue() == pytest.approx(original.equivalent_range_ue())
    assert loaded.largest_range_ue == pytest.approx(original.largest_range_ue)


def test_saving_a_spectrum_twice_replaces_its_bins(seeded_book: Path) -> None:
    meas.save_gauge(seeded_book, install())
    meas.save_campaign(seeded_book, campaign())
    meas.save_spectrum(seeded_book, "C-2025-04", spectrum())
    smaller = spec.build("G3-BF-01", [Cycle(range_ue=40.0, mean_ue=0.0, count=5.0)], 5.0)
    meas.save_spectrum(seeded_book, "C-2025-04", smaller)
    loaded = meas.load_spectrum(seeded_book, "C-2025-04", "G3-BF-01")
    assert len(loaded) == 1
    assert loaded.total_count == pytest.approx(5.0)


def test_the_quality_fractions_round_trip(seeded_book: Path) -> None:
    meas.save_gauge(seeded_book, install())
    meas.save_campaign(seeded_book, campaign())
    quality = SpectrumQuality(dropout_frac=0.12, railed_frac=0.03)
    meas.save_spectrum(seeded_book, "C-2025-04", spectrum(), quality)
    loaded = meas.load_quality(seeded_book, "C-2025-04", "G3-BF-01")
    assert loaded.dropout_frac == pytest.approx(0.12)
    assert loaded.railed_frac == pytest.approx(0.03)


def test_a_clean_record_is_trustworthy() -> None:
    assert SpectrumQuality().is_trustworthy
    assert SpectrumQuality().usable_frac == pytest.approx(1.0)


def test_any_railing_at_all_makes_a_record_untrustworthy() -> None:
    assert not SpectrumQuality(railed_frac=0.001).is_trustworthy


def test_a_little_dropout_is_tolerated() -> None:
    assert SpectrumQuality(dropout_frac=0.05).is_trustworthy
    assert not SpectrumQuality(dropout_frac=0.15).is_trustworthy


def test_the_usable_fraction_takes_both_off() -> None:
    quality = SpectrumQuality(dropout_frac=0.2, railed_frac=0.1)
    assert quality.usable_frac == pytest.approx(0.7)


def test_the_usable_fraction_never_goes_negative() -> None:
    assert SpectrumQuality(dropout_frac=0.8, railed_frac=0.5).usable_frac == 0.0


@pytest.mark.parametrize("kwargs", [{"dropout_frac": -0.1}, {"railed_frac": 1.5}])
def test_a_fraction_outside_the_range_is_refused(kwargs: dict[str, float]) -> None:
    with pytest.raises(StorageError, match="outside zero to one"):
        SpectrumQuality(**kwargs)


def test_reading_a_spectrum_that_is_not_there_is_refused(seeded_book: Path) -> None:
    with pytest.raises(StorageError, match="no spectrum"):
        meas.load_spectrum(seeded_book, "C-2025-04", "G3-BF-01")


def test_reading_quality_that_is_not_there_is_refused(seeded_book: Path) -> None:
    with pytest.raises(StorageError, match="no spectrum"):
        meas.load_quality(seeded_book, "C-2025-04", "G3-BF-01")


def test_the_gauges_in_a_campaign_come_back_in_order(seeded_book: Path) -> None:
    meas.save_gauge(seeded_book, install("G3-BF-02"))
    meas.save_gauge(seeded_book, install("G3-BF-01"))
    meas.save_campaign(seeded_book, campaign())
    meas.save_spectrum(seeded_book, "C-2025-04", spectrum("G3-BF-02"))
    meas.save_spectrum(seeded_book, "C-2025-04", spectrum("G3-BF-01"))
    assert meas.gauges_in_campaign(seeded_book, "C-2025-04") == ["G3-BF-01", "G3-BF-02"]


def test_a_campaign_with_no_spectra_reports_none(seeded_book: Path) -> None:
    meas.save_campaign(seeded_book, campaign())
    assert meas.gauges_in_campaign(seeded_book, "C-2025-04") == []


def test_correcting_a_campaign_keeps_its_spectra(seeded_book: Path) -> None:
    # An upsert rather than a delete and an insert. The cascade off campaigns
    # would otherwise take every count with the correction.
    meas.save_gauge(seeded_book, install())
    meas.save_campaign(seeded_book, campaign())
    meas.save_spectrum(seeded_book, "C-2025-04", spectrum())
    corrected = CampaignRecord(
        campaign_id="C-2025-04",
        structure_number="18-SH-0473",
        started_on=date(2025, 4, 1),
        ended_on=date(2025, 4, 14),
        seasonal_factor=1.4,
        note="corrected after the harvest count came in",
    )
    meas.save_campaign(seeded_book, corrected)
    assert meas.load_campaigns(seeded_book, "18-SH-0473")[0].seasonal_factor == pytest.approx(1.4)
    assert meas.load_spectrum(seeded_book, "C-2025-04", "G3-BF-01").total_count > 0.0


def test_recording_a_gauge_removal_keeps_its_spectra(seeded_book: Path) -> None:
    meas.save_gauge(seeded_book, install())
    meas.save_campaign(seeded_book, campaign())
    meas.save_spectrum(seeded_book, "C-2025-04", spectrum())
    meas.save_gauge(seeded_book, install(removed=date(2026, 2, 1)))
    assert meas.load_gauges(seeded_book)[0].removed_on == date(2026, 2, 1)
    assert meas.load_spectrum(seeded_book, "C-2025-04", "G3-BF-01").total_count > 0.0
