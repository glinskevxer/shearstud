"""The end to end fatigue evaluation, and the extrapolation it starts from."""

from __future__ import annotations

import math

import pytest

from shearstud.errors import InputError
from shearstud.fatigue import categories as cat
from shearstud.fatigue import evaluation as ev
from shearstud.fatigue.evaluation import Campaign, Evaluation
from shearstud.fatigue.life import TrafficModel
from shearstud.signals import spectrum as spec
from shearstud.signals.rainflow import Cycle
from shearstud.signals.spectrum import Spectrum

pytestmark = pytest.mark.fatigue

UE_PER_KSI = 1.0e6 / 29000.0


def measured(range_ksi: float = 5.0, count: float = 40000.0) -> Spectrum:
    cycles = [Cycle(range_ue=range_ksi * UE_PER_KSI, mean_ue=0.0, count=count)]
    return spec.build("G3-BF-01", cycles, 0.5)


def traffic(growth_pct: float = 2.0) -> TrafficModel:
    return TrafficModel(
        adtt=1500.0, lanes_available=2, growth_pct_per_yr=growth_pct, cycles_per_passage=1.0
    )


def evaluation(
    range_ksi: float = 5.0,
    count: float = 40000.0,
    category: str = "E",
    days: float = 14.0,
    seasonal: float = 1.0,
) -> Evaluation:
    return ev.evaluate(
        detail_id="G3-D07",
        measured=measured(range_ksi, count),
        campaign=Campaign(days=days, seasonal_factor=seasonal),
        detail=cat.category(category),
        traffic=traffic(),
    )


def test_a_two_week_campaign_scales_by_about_twenty_six() -> None:
    assert Campaign(days=14.0).annual_scale == pytest.approx(365.0 / 14.0)


def test_a_seasonal_factor_multiplies_the_scale() -> None:
    plain = Campaign(days=14.0).annual_scale
    corrected = Campaign(days=14.0, seasonal_factor=1.3).annual_scale
    assert corrected == pytest.approx(1.3 * plain)


def test_a_campaign_with_no_correction_says_it_is_typical() -> None:
    assert Campaign(days=30.0).is_typical
    assert not Campaign(days=30.0, seasonal_factor=0.8).is_typical


def test_a_campaign_too_short_to_see_a_week_is_refused() -> None:
    with pytest.raises(InputError, match="shorter than the 7.0 days"):
        Campaign(days=3.0)


def test_a_seasonal_factor_of_zero_is_refused() -> None:
    with pytest.raises(InputError, match="is not a factor"):
        Campaign(days=14.0, seasonal_factor=0.0)


def test_the_annual_spectrum_carries_the_scaled_counts() -> None:
    yearly = ev.annual_spectrum(measured(count=1000.0), Campaign(days=14.0))
    assert yearly.total_count == pytest.approx(1000.0 * 365.0 / 14.0)


def test_the_annual_spectrum_leaves_the_ranges_alone() -> None:
    m = measured()
    yearly = ev.annual_spectrum(m, Campaign(days=14.0))
    assert yearly.equivalent_range_ue() == pytest.approx(m.equivalent_range_ue())


def test_an_evaluation_reports_what_it_read() -> None:
    e = evaluation()
    assert e.detail_id == "G3-D07"
    assert e.detail_category == "E"
    assert e.campaign_days == pytest.approx(14.0)
    assert e.annual_cycles == pytest.approx(40000.0 * 365.0 / 14.0)
    assert e.effective_range_ksi == pytest.approx(5.0, rel=0.05)


def test_a_quiet_detail_at_a_strong_category_is_infinite_life() -> None:
    e = evaluation(range_ksi=3.0, category="B")
    assert e.infinite_life
    assert e.damage_per_first_year == 0.0
    assert math.isinf(e.years_remaining)
    assert e.is_comfortable
    assert e.verdict == "comfortable"


def test_the_same_traffic_at_a_weak_category_is_not() -> None:
    e = evaluation(range_ksi=3.0, category="E'")
    assert not e.infinite_life
    assert e.damage_per_first_year > 0.0


def test_a_bigger_stress_range_shortens_the_life() -> None:
    small = evaluation(range_ksi=5.0).years_remaining
    big = evaluation(range_ksi=9.0).years_remaining
    assert big < small


def test_more_cycles_shorten_the_life() -> None:
    few = evaluation(count=20000.0).years_remaining
    many = evaluation(count=80000.0).years_remaining
    assert many < few


def test_a_weaker_category_shortens_the_life() -> None:
    strong = evaluation(category="C").years_remaining
    weak = evaluation(category="E'").years_remaining
    assert weak < strong


def test_a_seasonal_correction_above_one_shortens_the_life() -> None:
    typical = evaluation(seasonal=1.0).years_remaining
    corrected = evaluation(seasonal=1.4).years_remaining
    assert corrected < typical


def test_damage_already_done_shortens_the_life() -> None:
    fresh = ev.evaluate(
        detail_id="d",
        measured=measured(range_ksi=9.0),
        campaign=Campaign(days=14.0),
        detail=cat.category("E"),
        traffic=traffic(growth_pct=0.0),
    )
    used = ev.evaluate(
        detail_id="d",
        measured=measured(range_ksi=9.0),
        campaign=Campaign(days=14.0),
        detail=cat.category("E"),
        traffic=traffic(growth_pct=0.0),
        damage_already_done=0.5,
    )
    assert used.years_remaining == pytest.approx(fresh.years_remaining / 2.0)


def test_an_evaluation_needs_a_detail_id() -> None:
    with pytest.raises(InputError, match="needs a detail id"):
        ev.evaluate(
            detail_id=" ",
            measured=measured(),
            campaign=Campaign(days=14.0),
            detail=cat.category("E"),
            traffic=traffic(),
        )


def test_a_short_life_asks_for_a_retrofit() -> None:
    e = evaluation(range_ksi=16.0, count=200000.0, category="E'")
    assert e.years_remaining < 5.0
    assert e.needs_retrofit
    assert e.verdict == "retrofit"


def test_the_three_verdicts_are_mutually_exclusive() -> None:
    for kwargs in ({"range_ksi": 3.0}, {"range_ksi": 9.0}, {"range_ksi": 16.0}):
        e = evaluation(category="E'", **kwargs)
        flags = [e.needs_retrofit, e.needs_watching, e.is_comfortable]
        assert sum(flags) == 1


def test_the_worst_detail_is_the_one_with_least_life() -> None:
    good = evaluation(range_ksi=3.0, category="B")
    bad = evaluation(range_ksi=16.0, category="E'")
    assert ev.worst_of([good, bad]) is bad


def test_choosing_between_no_evaluations_is_refused() -> None:
    with pytest.raises(InputError, match="no evaluations to choose"):
        ev.worst_of([])


def test_only_the_uncomfortable_details_need_attention() -> None:
    good = evaluation(range_ksi=3.0, category="B")
    bad = evaluation(range_ksi=16.0, category="E'")
    found = ev.needing_attention([good, bad])
    assert found == [bad]


def test_a_structure_of_comfortable_details_needs_nothing() -> None:
    good = evaluation(range_ksi=3.0, category="B")
    assert ev.needing_attention([good, good]) == []


def test_the_structure_life_is_its_worst_detail() -> None:
    good = evaluation(range_ksi=3.0, category="B")
    bad = evaluation(range_ksi=16.0, category="E'")
    assert ev.structure_life_years([good, bad]) == pytest.approx(bad.years_remaining)


def test_a_structure_of_infinite_life_details_is_indefinite() -> None:
    good = evaluation(range_ksi=3.0, category="B")
    assert ev.is_indefinite([good, good])


def test_one_finite_detail_makes_the_structure_finite() -> None:
    good = evaluation(range_ksi=3.0, category="B")
    bad = evaluation(range_ksi=16.0, category="E'")
    assert not ev.is_indefinite([good, bad])


def test_summarising_nothing_is_refused() -> None:
    with pytest.raises(InputError, match="no evaluations to summarise"):
        ev.structure_life_years([])
