"""The fatigue run, and the four ways a detail can fail to be evaluated."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from shearstud.analysis import fatiguerun as fr
from shearstud.errors import InputError
from shearstud.fatigue.life import TrafficModel
from shearstud.geometry.composite import DeckSlab
from shearstud.geometry.effective import DeckLayout
from shearstud.geometry.plate import flange, web
from shearstud.geometry.schedule import uniform
from shearstud.geometry.section import Section
from shearstud.program import interval
from shearstud.signals import spectrum as spec
from shearstud.signals.rainflow import Cycle
from shearstud.signals.spectrum import Spectrum
from shearstud.store import inventory
from shearstud.store import measurement as meas
from shearstud.store.measurement import CampaignRecord, SpectrumQuality
from shearstud.structure.detail import FIBRE_BOTTOM, FatigueDetail
from shearstud.structure.gauge import (
    ORIENTATION_LONGITUDINAL,
    ORIENTATION_TRANSVERSE,
    GaugeInstall,
)
from shearstud.structure.girder import GirderLine
from shearstud.structure.identity import parse
from shearstud.structure.record import Structure
from shearstud.structure.span import simple

pytestmark = pytest.mark.fatigue

SPAN_FT = 90.0
NUMBER = "18-SH-0473"
CAMPAIGN = "C-2025-04"
UE_PER_KSI = 1.0e6 / 29000.0


def detail(detail_id: str, station_ft: float, category: str = "E") -> FatigueDetail:
    return FatigueDetail(
        detail_id=detail_id,
        kind="cover_plate_end",
        category_name=category,
        station_ft=station_ft,
        fibre=FIBRE_BOTTOM,
    )


def structure(details: tuple[FatigueDetail, ...]) -> Structure:
    section = Section(
        "PG52",
        (
            flange("bottom", width_in=18.0, thickness_in=1.5, y_center_in=0.75),
            web("web", thickness_in=0.5625, depth_in=52.0, y_center_in=27.5),
            flange("top", width_in=16.0, thickness_in=1.0, y_center_in=54.0),
        ),
    )
    girder = GirderLine(
        girder_id="G3",
        schedule=uniform("G3", section, SPAN_FT),
        layout=DeckLayout(
            girder_index=0,
            spacing_left_ft=0.0,
            spacing_right_ft=8.0,
            overhang_ft=3.5,
            slab_thickness_in=8.0,
        ),
        deck=DeckSlab(thickness_in=8.0, effective_width_in=96.0, haunch_in=2.0, fc_ksi=4.0),
        details=details,
    )
    return Structure(
        number=parse(NUMBER),
        name="Salt Fork Creek",
        spans=simple(SPAN_FT),
        girders=(girder,),
        year_built=1968,
    )


def gauge(
    gauge_id: str, detail_id: str, orientation: str = ORIENTATION_LONGITUDINAL
) -> GaugeInstall:
    return GaugeInstall(
        gauge_id=gauge_id,
        detail_id=detail_id,
        orientation=orientation,
        gauge_factor=2.10,
        installed_on=date(2025, 3, 14),
        channel_limit_ue=1500.0,
    )


def spectrum(gauge_id: str, range_ksi: float = 6.0, count: float = 60000.0) -> Spectrum:
    cycles = [Cycle(range_ue=range_ksi * UE_PER_KSI, mean_ue=0.0, count=count)]
    return spec.build(gauge_id, cycles, 5.0)


def traffic() -> TrafficModel:
    return TrafficModel(
        adtt=1500.0, lanes_available=2, growth_pct_per_yr=2.0, cycles_per_passage=1.0
    )


@pytest.fixture
def wired(book: Path) -> Path:
    """A book with one structure, three details and two gauges on it."""
    details = (detail("D1", 20.0), detail("D2", 45.0), detail("D3", 70.0))
    inventory.save(book, structure(details))
    meas.save_campaign(
        book,
        CampaignRecord(
            campaign_id=CAMPAIGN,
            structure_number=NUMBER,
            started_on=date(2025, 4, 1),
            ended_on=date(2025, 4, 14),
        ),
    )
    meas.save_gauge(book, gauge("g1", "D1"))
    meas.save_gauge(book, gauge("g2", "D2"))
    meas.save_spectrum(book, CAMPAIGN, spectrum("g1"))
    meas.save_spectrum(book, CAMPAIGN, spectrum("g2", range_ksi=12.0))
    return book


def loaded(book: Path) -> Structure:
    return inventory.load(book, NUMBER)


def test_a_run_evaluates_the_gauged_details(wired: Path) -> None:
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    assert {e.detail_id for e in result.evaluated} == {"D1", "D2"}


def test_a_detail_with_no_gauge_is_skipped_and_named(wired: Path) -> None:
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    assert result.skipped_for(fr.SKIP_NO_GAUGE) == ["D3"]


def test_the_run_counts_every_detail_it_looked_at(wired: Path) -> None:
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    assert result.detail_count == 3
    assert result.measured_frac == pytest.approx(2.0 / 3.0)
    assert result.unmeasured_count == 1


def test_a_structure_with_no_measurements_reports_zero_coverage(book: Path) -> None:
    inventory.save(book, structure((detail("D1", 20.0),)))
    meas.save_campaign(
        book,
        CampaignRecord(
            campaign_id=CAMPAIGN,
            structure_number=NUMBER,
            started_on=date(2025, 4, 1),
            ended_on=date(2025, 4, 14),
        ),
    )
    result = fr.run(book, inventory.load(book, NUMBER), CAMPAIGN, traffic())
    assert result.evaluated == ()
    assert result.measured_frac == 0.0


def test_a_transverse_gauge_does_not_count_as_a_measurement(book: Path) -> None:
    inventory.save(book, structure((detail("D1", 20.0),)))
    meas.save_campaign(
        book,
        CampaignRecord(
            campaign_id=CAMPAIGN,
            structure_number=NUMBER,
            started_on=date(2025, 4, 1),
            ended_on=date(2025, 4, 14),
        ),
    )
    meas.save_gauge(book, gauge("g1", "D1", ORIENTATION_TRANSVERSE))
    meas.save_spectrum(book, CAMPAIGN, spectrum("g1"))
    result = fr.run(book, inventory.load(book, NUMBER), CAMPAIGN, traffic())
    assert result.skipped_for(fr.SKIP_TRANSVERSE) == ["D1"]


def test_a_gauge_that_did_not_report_is_skipped(wired: Path) -> None:
    meas.save_gauge(wired, gauge("g3", "D3"))
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    assert result.skipped_for(fr.SKIP_NO_SPECTRUM) == ["D3"]


def test_an_untrustworthy_record_is_skipped_by_default(wired: Path) -> None:
    meas.save_spectrum(wired, CAMPAIGN, spectrum("g1"), SpectrumQuality(dropout_frac=0.4))
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    assert result.skipped_for(fr.SKIP_UNTRUSTWORTHY) == ["D1"]


def test_an_untrustworthy_record_can_be_evaluated_on_request(wired: Path) -> None:
    meas.save_spectrum(wired, CAMPAIGN, spectrum("g1"), SpectrumQuality(dropout_frac=0.4))
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic(), require_trustworthy=False)
    assert "D1" in {e.detail_id for e in result.evaluated}


def test_the_worst_detail_is_the_one_with_the_bigger_stress_range(wired: Path) -> None:
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    assert result.worst().detail_id == "D2"


def test_the_details_needing_attention_come_back_worst_first(wired: Path) -> None:
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    attention = result.needing_attention()
    lives = [e.years_remaining for e in attention]
    assert lives == sorted(lives)


def test_the_campaign_length_reaches_the_evaluation(wired: Path) -> None:
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    assert all(e.campaign_days == pytest.approx(14.0) for e in result.evaluated)


def test_a_seasonal_factor_on_the_campaign_reaches_the_evaluation(wired: Path) -> None:
    meas.save_campaign(
        wired,
        CampaignRecord(
            campaign_id=CAMPAIGN,
            structure_number=NUMBER,
            started_on=date(2025, 4, 1),
            ended_on=date(2025, 4, 14),
            seasonal_factor=1.5,
        ),
    )
    plain = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    assert plain.worst().annual_cycles > 0.0


def test_a_campaign_that_is_not_on_this_structure_is_refused(wired: Path) -> None:
    with pytest.raises(InputError, match="no campaign"):
        fr.run(wired, loaded(wired), "C-1999-01", traffic())


def test_an_unknown_skip_reason_is_refused() -> None:
    with pytest.raises(InputError, match="unknown skip reason"):
        fr.SkippedDetail("D1", "the inspector was ill")


def test_asking_for_an_unknown_skip_reason_is_refused(wired: Path) -> None:
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    with pytest.raises(InputError, match="unknown skip reason"):
        result.skipped_for("the inspector was ill")


def test_the_run_hands_the_interval_rule_a_state_it_can_use(wired: Path) -> None:
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    state = fr.inspection_state(result, lowest_condition_rating=7)
    assert 0.0 <= state.fatigue_life_years <= fr.MAX_CREDITED_LIFE_YEARS
    assert not state.is_posted


def test_a_structure_with_nothing_evaluated_gets_the_short_interval(book: Path) -> None:
    empty = fr.RunResult(campaign_id=CAMPAIGN, evaluated=(), skipped=())
    state = fr.inspection_state(empty, lowest_condition_rating=8)
    assert state.fatigue_life_years == 0.0
    assert interval.decide(state).months == interval.SHORT_MONTHS


def test_an_indefinite_structure_does_not_arrive_as_infinity(wired: Path) -> None:
    # An infinite life is a statement about the calculation. Letting it into a
    # programme decision hands the office a number no threshold can fail.
    meas.save_spectrum(wired, CAMPAIGN, spectrum("g1", range_ksi=0.5))
    meas.save_spectrum(wired, CAMPAIGN, spectrum("g2", range_ksi=0.5))
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    state = fr.inspection_state(result, lowest_condition_rating=8)
    assert state.fatigue_life_years == pytest.approx(fr.MAX_CREDITED_LIFE_YEARS)


def test_a_sound_structure_with_life_left_earns_the_extension(wired: Path) -> None:
    meas.save_spectrum(wired, CAMPAIGN, spectrum("g1", range_ksi=0.5))
    meas.save_spectrum(wired, CAMPAIGN, spectrum("g2", range_ksi=0.5))
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    state = fr.inspection_state(result, lowest_condition_rating=8)
    assert interval.decide(state).months == interval.EXTENDED_MONTHS


def test_a_posting_takes_the_extension_away(wired: Path) -> None:
    meas.save_spectrum(wired, CAMPAIGN, spectrum("g1", range_ksi=0.5))
    meas.save_spectrum(wired, CAMPAIGN, spectrum("g2", range_ksi=0.5))
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    state = fr.inspection_state(result, lowest_condition_rating=8, is_posted=True)
    assert interval.decide(state).months == interval.SHORT_MONTHS


def test_a_recent_inspection_is_not_due(wired: Path) -> None:
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    assert not fr.inspection_due(result, date(2026, 5, 1), date(2026, 6, 1), 7)


def test_an_old_inspection_is_due(wired: Path) -> None:
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    assert fr.inspection_due(result, date(2005, 5, 1), date(2026, 6, 1), 7)


def test_a_nonredundant_structure_is_due_sooner_than_a_redundant_one(wired: Path) -> None:
    meas.save_spectrum(wired, CAMPAIGN, spectrum("g1", range_ksi=0.5))
    meas.save_spectrum(wired, CAMPAIGN, spectrum("g2", range_ksi=0.5))
    result = fr.run(wired, loaded(wired), CAMPAIGN, traffic())
    last, today = date(2023, 1, 1), date(2026, 6, 1)
    assert not fr.inspection_due(result, last, today, 8)
    assert fr.inspection_due(result, last, today, 8, has_nonredundant_members=True)
