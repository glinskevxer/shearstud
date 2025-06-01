"""Detail categories, their published constants, and the S-N curve."""

from __future__ import annotations

import math

import pytest

from shearstud.errors import ConfigError
from shearstud.fatigue import categories as cat

pytestmark = pytest.mark.fatigue

PUBLISHED = {
    "A": (250.0e8, 24.0),
    "B": (120.0e8, 16.0),
    "B'": (61.0e8, 12.0),
    "C": (44.0e8, 10.0),
    "C'": (44.0e8, 12.0),
    "D": (22.0e8, 7.0),
    "E": (11.0e8, 4.5),
    "E'": (3.9e8, 2.6),
}


@pytest.mark.parametrize("name,expected", sorted(PUBLISHED.items()))
def test_the_constants_are_the_published_ones(name: str, expected: tuple[float, float]) -> None:
    c = cat.category(name)
    assert c.constant_a == pytest.approx(expected[0])
    assert c.threshold_ksi == pytest.approx(expected[1])


def test_the_table_covers_exactly_the_published_categories() -> None:
    assert set(cat.NAMES) == set(PUBLISHED)


def test_the_categories_get_weaker_down_the_list() -> None:
    constants = [c.constant_a for c in cat.categories()]
    assert constants == sorted(constants, reverse=True)


def test_e_prime_is_far_weaker_than_a() -> None:
    ratio = cat.category("A").constant_a / cat.category("E'").constant_a
    assert ratio > 60.0


def test_c_and_c_prime_share_a_constant_but_not_a_threshold() -> None:
    c = cat.category("C")
    c_prime = cat.category("C'")
    assert c.constant_a == pytest.approx(c_prime.constant_a)
    assert c_prime.threshold_ksi > c.threshold_ksi


@pytest.mark.parametrize(
    "spelling", ["e'", "E'", " ep ", "EP", "eprime", "E PRIME".replace(" ", "")]
)
def test_a_prime_can_be_spelled_several_ways(spelling: str) -> None:
    assert cat.category(spelling).name == "E'"


def test_an_unknown_category_lists_the_known_ones() -> None:
    with pytest.raises(ConfigError, match="unknown detail category"):
        cat.category("F")


def test_every_category_carries_an_example() -> None:
    for c in cat.categories():
        assert c.example.strip()


def test_the_curve_gives_the_constant_at_one_ksi() -> None:
    c = cat.category("A")
    assert c.cycles_to_failure(30.0) == pytest.approx(250.0e8 / 27000.0)


def test_doubling_the_range_cuts_the_life_by_eight() -> None:
    c = cat.category("C")
    assert c.cycles_to_failure(20.0) == pytest.approx(c.cycles_to_failure(40.0) * 8.0)


def test_a_range_below_the_threshold_never_fails() -> None:
    c = cat.category("C")
    assert c.cycles_to_failure(9.9) == math.inf
    assert c.is_infinite_life(9.9)


def test_a_range_at_the_threshold_is_finite() -> None:
    c = cat.category("C")
    assert math.isfinite(c.cycles_to_failure(10.0))
    assert not c.is_infinite_life(10.0)


def test_a_stress_range_of_zero_is_refused() -> None:
    with pytest.raises(ConfigError, match="is not a range"):
        cat.category("C").cycles_to_failure(0.0)


def test_the_curve_inverts() -> None:
    c = cat.category("D")
    life = c.cycles_to_failure(15.0)
    assert c.range_for_cycles_ksi(life) == pytest.approx(15.0)


def test_a_longer_life_demands_a_lower_range() -> None:
    c = cat.category("D")
    assert c.range_for_cycles_ksi(1.0e8) < c.range_for_cycles_ksi(1.0e6)


def test_a_life_of_zero_cycles_is_refused() -> None:
    with pytest.raises(ConfigError, match="is not a life"):
        cat.category("D").range_for_cycles_ksi(0.0)


def test_fatigue_one_resistance_is_the_threshold_whatever_the_life() -> None:
    c = cat.category("E")
    assert c.resistance_ksi(1.0e5, infinite_life=True) == pytest.approx(4.5)
    assert c.resistance_ksi(1.0e9, infinite_life=True) == pytest.approx(4.5)


def test_fatigue_two_resistance_follows_the_life() -> None:
    c = cat.category("E")
    short = c.resistance_ksi(1.0e5, infinite_life=False)
    long = c.resistance_ksi(1.0e8, infinite_life=False)
    assert short > long


def test_fatigue_two_beats_fatigue_one_at_a_short_life() -> None:
    # A detail that fails the infinite life check can still have plenty of
    # finite life, which is the whole point of having two limit states.
    c = cat.category("E")
    assert c.resistance_ksi(1.0e5, infinite_life=False) > c.threshold_ksi


def test_the_weakest_of_a_set_governs() -> None:
    assert cat.weakest_of(["B", "E'", "C"]).name == "E'"


def test_the_weakest_of_one_is_that_one() -> None:
    assert cat.weakest_of(["C'"]).name == "C'"


def test_the_weakest_of_nothing_is_refused() -> None:
    with pytest.raises(ConfigError, match="no detail categories"):
        cat.weakest_of([])


def test_the_weakest_of_a_set_with_an_unknown_name_is_refused() -> None:
    with pytest.raises(ConfigError, match="unknown detail category"):
        cat.weakest_of(["C", "Z"])


def test_a_weaker_detail_always_fails_sooner_at_the_same_range() -> None:
    for stronger, weaker in zip(cat.NAMES, cat.NAMES[1:], strict=False):
        a = cat.category(stronger)
        b = cat.category(weaker)
        assert a.cycles_to_failure(30.0) >= b.cycles_to_failure(30.0)
