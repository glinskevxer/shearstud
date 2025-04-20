"""Live load assembly, and the ordering that the four steps have to keep."""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.loads import vehicles
from shearstud.loads.continuous import continuous_moment
from shearstud.loads.influence import simple_moment
from shearstud.loads.live import LiveLoadCase, envelope, evaluate, ratio_to

pytestmark = pytest.mark.loads


def case(
    span_ft: float = 80.0,
    df: float = 0.65,
    allowance: float = 0.33,
    lane_klf: float = 0.64,
) -> LiveLoadCase:
    return LiveLoadCase(
        label="G3 midspan",
        influence=simple_moment(span_ft, span_ft / 2.0),
        distribution_factor=df,
        allowance_frac=allowance,
        lane_load_klf=lane_klf,
    )


def test_the_static_truck_effect_is_the_placement_value() -> None:
    effect = evaluate(case(), vehicles.design_truck())
    assert effect.static_truck == pytest.approx(effect.placement.value)


def test_impact_lands_on_the_truck_only() -> None:
    effect = evaluate(case(), vehicles.design_truck())
    assert effect.truck_with_impact == pytest.approx(effect.static_truck * 1.33)


def test_the_lane_load_arrives_after_impact() -> None:
    effect = evaluate(case(), vehicles.design_truck())
    assert effect.per_lane == pytest.approx(effect.truck_with_impact + effect.lane)


def test_the_distribution_factor_is_applied_last_to_everything() -> None:
    effect = evaluate(case(df=0.65), vehicles.design_truck())
    assert effect.distributed == pytest.approx(effect.per_lane * 0.65)


def test_distributing_before_the_lane_load_would_give_a_different_answer() -> None:
    effect = evaluate(case(df=0.65), vehicles.design_truck())
    wrong = effect.truck_with_impact * 0.65 + effect.lane
    assert wrong != pytest.approx(effect.distributed)


def test_the_lane_load_on_an_eighty_foot_span_is_the_area_times_the_load() -> None:
    effect = evaluate(case(span_ft=80.0, lane_klf=0.64), vehicles.design_truck())
    assert effect.lane == pytest.approx(0.64 * 80.0**2 / 8.0)


def test_no_lane_load_leaves_the_per_lane_effect_as_the_truck() -> None:
    effect = evaluate(case(lane_klf=0.0), vehicles.design_truck())
    assert effect.per_lane == pytest.approx(effect.truck_with_impact)
    assert effect.lane == pytest.approx(0.0)


def test_the_impact_share_is_a_sensible_fraction() -> None:
    effect = evaluate(case(), vehicles.design_truck())
    assert 0.0 < effect.impact_share < 0.33


def test_the_impact_share_is_zero_when_there_is_no_effect() -> None:
    effect = evaluate(
        LiveLoadCase(
            label="zero",
            influence=simple_moment(80.0, 0.0),
            distribution_factor=0.65,
            allowance_frac=0.33,
        ),
        vehicles.design_truck(),
    )
    assert effect.per_lane == pytest.approx(0.0)
    assert effect.impact_share == 0.0


def test_a_larger_allowance_gives_a_larger_answer() -> None:
    low = evaluate(case(allowance=0.10), vehicles.design_truck()).distributed
    high = evaluate(case(allowance=0.33), vehicles.design_truck()).distributed
    assert high > low


def test_the_effect_carries_the_case_and_vehicle_names() -> None:
    effect = evaluate(case(), vehicles.vehicle("TYPE3S2"))
    assert effect.case == "G3 midspan"
    assert effect.vehicle == "TYPE3S2"


def test_asking_for_a_minimum_uses_the_negative_lane_placement() -> None:
    negative_case = LiveLoadCase(
        label="pier",
        influence=continuous_moment([100.0, 100.0], 0, 50.0),
        distribution_factor=0.7,
        allowance_frac=0.33,
        lane_load_klf=0.64,
    )
    worst = evaluate(negative_case, vehicles.design_truck(), maximum=False)
    assert worst.distributed < 0.0
    assert worst.lane < 0.0


def test_the_envelope_picks_the_governing_vehicle() -> None:
    c = case()
    fleet = vehicles.legal_fleet()
    best = envelope(c, fleet)
    for train in fleet:
        assert evaluate(c, train).distributed <= best.distributed + 1e-9


def test_the_envelope_of_one_vehicle_is_that_vehicle() -> None:
    c = case()
    t = vehicles.vehicle("TYPE3")
    assert envelope(c, [t]).vehicle == "TYPE3"


def test_a_minimum_envelope_takes_the_most_negative() -> None:
    negative_case = LiveLoadCase(
        label="pier",
        influence=continuous_moment([100.0, 100.0], 0, 50.0),
        distribution_factor=0.7,
        allowance_frac=0.33,
    )
    fleet = vehicles.legal_fleet()
    worst = envelope(negative_case, fleet, maximum=False)
    for train in fleet:
        assert evaluate(negative_case, train, maximum=False).distributed >= worst.distributed - 1e-9


def test_an_empty_envelope_names_the_case() -> None:
    with pytest.raises(InputError, match="G3 midspan"):
        envelope(case(), [])


def test_a_ratio_compares_two_effects() -> None:
    heavy = evaluate(case(), vehicles.vehicle("TYPE3-3"))
    light = evaluate(case(), vehicles.vehicle("TYPE3"))
    assert ratio_to(heavy, light) > 1.0


def test_a_ratio_against_nothing_is_refused() -> None:
    zero_case = LiveLoadCase(
        label="zero",
        influence=simple_moment(80.0, 0.0),
        distribution_factor=0.65,
        allowance_frac=0.33,
    )
    zero = evaluate(zero_case, vehicles.design_truck())
    with pytest.raises(InputError, match="zero effect"):
        ratio_to(zero, zero)


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"distribution_factor": 0.0}, "not positive"),
        ({"allowance_frac": -0.1}, "is negative"),
        ({"lane_load_klf": -0.5}, "is negative"),
        ({"label": " "}, "needs a label"),
    ],
)
def test_a_bad_case_field_is_refused(kwargs: dict[str, object], message: str) -> None:
    base = {
        "label": "G3",
        "influence": simple_moment(80.0, 40.0),
        "distribution_factor": 0.65,
        "allowance_frac": 0.33,
        "lane_load_klf": 0.64,
    }
    with pytest.raises(InputError, match=message):
        LiveLoadCase(**{**base, **kwargs})  # type: ignore[arg-type]
