"""Miner damage, and the two questions a measured spectrum gets asked."""

from __future__ import annotations

import math

import pytest

from shearstud.errors import InputError
from shearstud.fatigue import categories as cat
from shearstud.fatigue import damage
from shearstud.signals import spectrum as spec
from shearstud.signals.rainflow import Cycle
from shearstud.signals.spectrum import Spectrum

pytestmark = pytest.mark.fatigue

#: 100 microstrain is 2.9 ksi in steel, which is the conversion every number
#: below is built from.
UE_PER_KSI = 1.0e6 / 29000.0


def spectrum_at(range_ksi: float, count: float, gauge: str = "G3-BF-01") -> Spectrum:
    """A one bin spectrum at a chosen stress range."""
    range_ue = range_ksi * UE_PER_KSI
    return spec.build(gauge, [Cycle(range_ue=range_ue, mean_ue=0.0, count=count)], 0.1)


def mixed_spectrum() -> Spectrum:
    cycles = [
        Cycle(range_ue=2.0 * UE_PER_KSI, mean_ue=0.0, count=50000.0),
        Cycle(range_ue=8.0 * UE_PER_KSI, mean_ue=0.0, count=2000.0),
        Cycle(range_ue=16.0 * UE_PER_KSI, mean_ue=0.0, count=40.0),
    ]
    return spec.build("G3-BF-01", cycles, 0.1)


def test_a_single_bin_converts_to_the_stress_range_it_was_built_from() -> None:
    bins = damage.stress_bins_ksi(spectrum_at(12.0, 100.0))
    assert len(bins) == 1
    assert bins[0][0] == pytest.approx(12.0, rel=1e-3)
    assert bins[0][1] == pytest.approx(100.0)


def test_a_softer_modulus_reads_a_lower_stress_for_the_same_strain() -> None:
    s = spectrum_at(12.0, 100.0)
    stiff = damage.effective_range_ksi(s, 29000.0)
    soft = damage.effective_range_ksi(s, 10000.0)
    assert soft < stiff


def test_a_modulus_of_zero_is_refused() -> None:
    with pytest.raises(InputError, match="is not a modulus"):
        damage.stress_bins_ksi(spectrum_at(12.0, 100.0), 0.0)


def test_the_effective_range_of_one_size_is_that_size() -> None:
    s = spectrum_at(14.0, 5000.0)
    assert damage.effective_range_ksi(s) == pytest.approx(14.0, rel=1e-3)


def test_the_effective_range_of_a_mixture_is_pulled_up_by_the_tail() -> None:
    s = mixed_spectrum()
    counts = [b.count for b in s.bins]
    ranges = [b.representative_ue / UE_PER_KSI for b in s.bins]
    arithmetic = sum(c * r for c, r in zip(counts, ranges, strict=True)) / sum(counts)
    assert damage.effective_range_ksi(s) > arithmetic


def test_the_effective_range_of_an_empty_spectrum_is_zero() -> None:
    empty = spec.build("G1", [], 5.0)
    assert damage.effective_range_ksi(empty) == 0.0
    assert damage.largest_range_ksi(empty) == 0.0


def test_a_bad_exponent_is_refused() -> None:
    with pytest.raises(InputError, match="is not positive"):
        damage.effective_range_ksi(spectrum_at(10.0, 1.0), exponent=0.0)


def test_the_largest_range_is_the_top_bin() -> None:
    assert damage.largest_range_ksi(mixed_spectrum()) == pytest.approx(16.0, rel=0.02)


def test_a_quiet_spectrum_at_a_strong_detail_is_infinite_life() -> None:
    s = spectrum_at(2.0, 500000.0)
    assert damage.has_infinite_life(s, cat.category("B"))


def test_the_same_spectrum_at_a_weak_detail_is_not() -> None:
    s = spectrum_at(2.0, 500000.0)
    assert not damage.has_infinite_life(s, cat.category("E'"))


def test_the_threshold_is_halved_before_the_comparison() -> None:
    # Category C threshold is 10 ksi, so an effective range of 6 is over the
    # half threshold of 5 even though it is well under the threshold itself.
    s = spectrum_at(6.0, 1000.0)
    c = cat.category("C")
    assert c.threshold_ksi > 6.0
    assert not damage.has_infinite_life(s, c)


def test_the_truncation_fraction_can_be_moved() -> None:
    s = spectrum_at(6.0, 1000.0)
    c = cat.category("C")
    assert damage.has_infinite_life(s, c, truncation_frac=1.0)
    assert not damage.has_infinite_life(s, c, truncation_frac=0.5)


@pytest.mark.parametrize("frac", [0.0, -0.5, 1.5])
def test_a_truncation_fraction_off_the_range_is_refused(frac: float) -> None:
    with pytest.raises(InputError, match="outside zero to one"):
        damage.has_infinite_life(spectrum_at(6.0, 10.0), cat.category("C"), truncation_frac=frac)


def test_damage_at_a_known_range_matches_the_curve() -> None:
    c = cat.category("C")
    life = c.cycles_to_failure(20.0)
    result = damage.accumulate(spectrum_at(20.0, life), c)
    assert result.damage == pytest.approx(1.0, rel=0.01)


def test_half_the_life_is_half_the_damage() -> None:
    c = cat.category("C")
    life = c.cycles_to_failure(20.0)
    result = damage.accumulate(spectrum_at(20.0, life / 2.0), c)
    assert result.damage == pytest.approx(0.5, rel=0.01)


def test_damage_is_linear_in_the_cycle_count() -> None:
    c = cat.category("D")
    one = damage.accumulate(spectrum_at(18.0, 1000.0), c).damage
    ten = damage.accumulate(spectrum_at(18.0, 10000.0), c).damage
    assert ten == pytest.approx(10.0 * one)


def test_damage_goes_as_the_cube_of_the_range() -> None:
    c = cat.category("D")
    small = damage.accumulate(spectrum_at(10.0, 1000.0), c).damage
    big = damage.accumulate(spectrum_at(20.0, 1000.0), c).damage
    assert big == pytest.approx(8.0 * small, rel=0.02)


def test_a_weaker_detail_takes_more_damage_from_the_same_spectrum() -> None:
    s = mixed_spectrum()
    strong = damage.accumulate(s, cat.category("B")).damage
    weak = damage.accumulate(s, cat.category("E'")).damage
    assert weak > strong


def test_an_infinite_life_result_records_no_damage() -> None:
    result = damage.accumulate(spectrum_at(2.0, 500000.0), cat.category("B"))
    assert result.infinite_life
    assert result.damage == 0.0
    assert not result.is_damaged
    assert result.cycles_remaining() == math.inf


def test_the_result_carries_what_it_was_computed_from() -> None:
    result = damage.accumulate(mixed_spectrum(), cat.category("E"))
    assert result.detail_category == "E"
    assert result.cycles_counted == pytest.approx(52040.0)
    assert result.effective_range_ksi > 0.0
    assert result.largest_range_ksi == pytest.approx(16.0, rel=0.02)


def test_cycles_remaining_is_the_damage_inverted() -> None:
    c = cat.category("D")
    life = c.cycles_to_failure(18.0)
    result = damage.accumulate(spectrum_at(18.0, life / 4.0), c)
    assert result.cycles_remaining() == pytest.approx(3.0, rel=0.02)


def test_nothing_left_when_the_damage_has_run_out() -> None:
    c = cat.category("D")
    life = c.cycles_to_failure(18.0)
    result = damage.accumulate(spectrum_at(18.0, life), c)
    assert result.cycles_remaining() == pytest.approx(0.0, abs=0.02)


def test_an_empty_spectrum_leaves_everything_remaining() -> None:
    result = damage.accumulate(spec.build("G1", [], 5.0), cat.category("E"))
    assert result.cycles_remaining() == math.inf


def test_damage_from_several_campaigns_adds_up() -> None:
    c = cat.category("D")
    a = damage.accumulate(spectrum_at(18.0, 5000.0), c)
    b = damage.accumulate(spectrum_at(22.0, 3000.0), c)
    assert damage.combine([a, b]) == pytest.approx(a.damage + b.damage)


def test_combining_infinite_life_results_gives_nothing() -> None:
    c = cat.category("B")
    quiet = damage.accumulate(spectrum_at(2.0, 100000.0), c)
    assert damage.combine([quiet, quiet]) == 0.0


def test_one_cycle_of_damage_matches_the_curve() -> None:
    c = cat.category("C")
    per_cycle = damage.damage_per_cycle(20.0, c)
    assert per_cycle == pytest.approx(1.0 / c.cycles_to_failure(20.0))


def test_a_zero_range_cycle_does_no_damage_and_is_refused() -> None:
    with pytest.raises(InputError, match="is not a range"):
        damage.damage_per_cycle(0.0, cat.category("C"))
