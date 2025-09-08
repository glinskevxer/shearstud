"""Posting: three decisions that are policy rather than mechanics."""

from __future__ import annotations

import math

import pytest

from shearstud.errors import InputError
from shearstud.rating import posting as post
from shearstud.rating.rate import RatingFactor

pytestmark = pytest.mark.rating


def rating(value: float, vehicle: str = "TYPE3", gross_kip: float = 50.0) -> RatingFactor:
    """A rating whose factor comes out at exactly ``value``."""
    return RatingFactor(
        label=f"{vehicle} at {value}",
        vehicle=vehicle,
        capacity=1000.0,
        factored_dead=0.0,
        factored_live=1000.0 / value,
        gross_weight_kip=gross_kip,
    )


def ratings(single: float, semi: float, combination: float) -> dict[str, RatingFactor]:
    return {
        "single_unit": rating(single, "TYPE3", 50.0),
        "semi": rating(semi, "TYPE3S2", 72.0),
        "combination": rating(combination, "TYPE3-3", 80.0),
    }


def test_a_rating_above_one_is_not_posted() -> None:
    assert math.isinf(post.posted_tons(rating(1.4)))


def test_a_rating_of_exactly_one_is_not_posted() -> None:
    assert math.isinf(post.posted_tons(rating(1.0)))


def test_a_rating_below_one_gives_a_weight() -> None:
    # 0.8 of a 50 kip vehicle is 40 kip, which is 20 tons.
    assert post.posted_tons(rating(0.8, gross_kip=50.0)) == pytest.approx(20.0)


def test_the_weight_always_rounds_down() -> None:
    # 0.985 of 50 kip is 24.6 tons, and the sign says 24.
    assert post.posted_tons(rating(0.985, gross_kip=50.0)) == pytest.approx(24.0)


def test_rounding_down_never_adds_load() -> None:
    for value in (0.51, 0.62, 0.735, 0.88, 0.99):
        r = rating(value, gross_kip=72.0)
        assert post.posted_tons(r) <= r.tonnage_tons()


def test_a_structure_that_rates_everywhere_stays_open() -> None:
    decision = post.decide(ratings(1.4, 1.2, 1.05))
    assert decision.outcome == post.OPEN
    assert decision.posted_lines == ()
    assert math.isinf(decision.lowest_tons)


def test_one_failing_vehicle_posts_the_structure() -> None:
    decision = post.decide(ratings(1.4, 1.2, 0.85))
    assert decision.outcome == post.POSTED
    assert len(decision.posted_lines) == 1
    assert decision.posted_lines[0].silhouette == "combination"


def test_the_open_silhouettes_stay_off_the_sign() -> None:
    decision = post.decide(ratings(1.4, 1.2, 0.85))
    posted = {line.silhouette for line in decision.posted_lines}
    assert posted == {"combination"}


def test_a_very_low_rating_closes_the_structure() -> None:
    decision = post.decide(ratings(0.25, 0.6, 0.5))
    assert decision.outcome == post.CLOSED


def test_the_closure_threshold_is_where_it_says_it_is() -> None:
    just_above = post.decide(ratings(0.31, 1.2, 1.05))
    just_below = post.decide(ratings(0.29, 1.2, 1.05))
    assert just_above.outcome == post.POSTED
    assert just_below.outcome == post.CLOSED


def test_the_governing_factor_is_the_worst_one() -> None:
    decision = post.decide(ratings(1.4, 0.72, 0.85))
    assert decision.governing_factor == pytest.approx(0.72)


def test_the_lowest_posted_weight_is_reported() -> None:
    decision = post.decide(ratings(0.8, 0.9, 0.7))
    assert decision.lowest_tons == min(line.tons for line in decision.posted_lines)


def test_every_silhouette_appears_on_the_decision() -> None:
    decision = post.decide(ratings(1.4, 1.2, 1.05))
    assert {line.silhouette for line in decision.lines} == set(post.SIGN_VEHICLES)


def test_each_line_carries_the_vehicle_that_produced_it() -> None:
    decision = post.decide(ratings(0.8, 0.9, 0.7))
    by_silhouette = {line.silhouette: line.vehicle for line in decision.lines}
    assert by_silhouette == post.SIGN_VEHICLES


def test_a_missing_silhouette_is_refused() -> None:
    incomplete = ratings(0.8, 0.9, 0.7)
    del incomplete["semi"]
    with pytest.raises(InputError, match="no rating for the semi silhouette"):
        post.decide(incomplete)


def test_a_line_below_the_minimum_weight_says_so() -> None:
    decision = post.decide(ratings(0.1, 1.2, 1.05))
    single = next(line for line in decision.lines if line.silhouette == "single_unit")
    assert single.is_below_the_minimum


def test_a_normal_posted_line_is_not_below_the_minimum() -> None:
    decision = post.decide(ratings(0.8, 1.2, 1.05))
    single = next(line for line in decision.lines if line.silhouette == "single_unit")
    assert single.is_posted
    assert not single.is_below_the_minimum


def test_an_unposted_line_is_never_below_the_minimum() -> None:
    decision = post.decide(ratings(1.4, 1.2, 1.05))
    assert not any(line.is_below_the_minimum for line in decision.lines)


def test_an_open_structure_gets_no_sign() -> None:
    assert post.sign_text(post.decide(ratings(1.4, 1.2, 1.05))) == []


def test_a_closed_structure_gets_one_line() -> None:
    assert post.sign_text(post.decide(ratings(0.2, 1.2, 1.05))) == ["BRIDGE CLOSED"]


def test_a_posted_structure_gets_a_line_per_failing_vehicle() -> None:
    text = post.sign_text(post.decide(ratings(0.8, 0.9, 0.7)))
    assert len(text) == 3
    assert all("TONS" in line for line in text)


def test_the_sign_reads_in_silhouette_order() -> None:
    text = post.sign_text(post.decide(ratings(0.8, 0.9, 0.7)))
    assert text[0].startswith("SINGLE UNIT")
    assert text[1].startswith("SEMI")
    assert text[2].startswith("COMBINATION")


def test_the_sign_carries_whole_tons() -> None:
    text = post.sign_text(post.decide(ratings(0.985, 1.2, 1.05)))
    assert text == ["SINGLE UNIT 24 TONS"]


def test_an_unknown_outcome_is_refused() -> None:
    with pytest.raises(InputError, match="unknown posting outcome"):
        post.PostingDecision(outcome="restricted", lines=(), governing_factor=1.0)
