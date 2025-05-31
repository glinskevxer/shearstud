"""Cycle histograms, and the bias the representative range is there to remove."""

from __future__ import annotations

import pytest

from shearstud.errors import RecordError
from shearstud.signals import spectrum as spec
from shearstud.signals.rainflow import Cycle
from shearstud.signals.spectrum import Spectrum, SpectrumBin

pytestmark = pytest.mark.signals


def cycles(pairs: list[tuple[float, float]]) -> list[Cycle]:
    return [Cycle(range_ue=r, mean_ue=0.0, count=c) for r, c in pairs]


def test_one_cycle_lands_in_one_bin() -> None:
    s = spec.build("G1", cycles([(23.0, 1.0)]), bin_width_ue=5.0)
    assert len(s) == 1
    assert s.bins[0].low_ue == pytest.approx(20.0)
    assert s.total_count == pytest.approx(1.0)


def test_cycles_in_the_same_bin_add_up() -> None:
    s = spec.build("G1", cycles([(21.0, 2.0), (24.0, 3.0)]), bin_width_ue=5.0)
    assert len(s) == 1
    assert s.total_count == pytest.approx(5.0)


def test_bins_come_back_in_ascending_order() -> None:
    s = spec.build("G1", cycles([(90.0, 1.0), (10.0, 1.0), (50.0, 1.0)]))
    assert [b.low_ue for b in s.bins] == pytest.approx([10.0, 50.0, 90.0])


def test_a_bin_boundary_goes_to_the_upper_bin() -> None:
    s = spec.build("G1", cycles([(25.0, 1.0)]), bin_width_ue=5.0)
    assert s.bins[0].low_ue == pytest.approx(25.0)


def test_the_representative_sits_inside_its_own_bin() -> None:
    s = spec.build("G1", cycles([(21.0, 5.0), (24.9, 1.0)]), bin_width_ue=5.0)
    b = s.bins[0]
    assert b.low_ue <= b.representative_ue <= b.high_ue


def test_the_representative_beats_the_midpoint_on_a_wide_bin() -> None:
    # All the cycles sit in the top of the bin, so the midpoint understates them.
    wide = spec.build("G1", cycles([(48.0, 10.0), (49.0, 10.0)]), bin_width_ue=50.0)
    b = wide.bins[0]
    assert b.midpoint_ue == pytest.approx(25.0)
    assert b.representative_ue > 45.0


def test_the_representative_is_cube_weighted_not_averaged() -> None:
    s = spec.build("G1", cycles([(10.0, 1.0), (19.0, 1.0)]), bin_width_ue=20.0)
    arithmetic = 14.5
    assert s.bins[0].representative_ue > arithmetic


def test_the_equivalent_range_of_one_size_is_that_size() -> None:
    s = spec.build("G1", cycles([(40.0, 100.0)]), bin_width_ue=1.0)
    assert s.equivalent_range_ue() == pytest.approx(40.0, rel=0.02)


def test_the_equivalent_range_of_an_empty_spectrum_is_zero() -> None:
    s = spec.build("G1", [], bin_width_ue=5.0)
    assert s.equivalent_range_ue() == 0.0
    assert s.largest_range_ue == 0.0
    assert s.total_count == 0.0


def test_the_largest_range_comes_from_the_top_occupied_bin() -> None:
    s = spec.build("G1", cycles([(12.0, 4.0), (87.0, 1.0)]), bin_width_ue=5.0)
    assert s.largest_range_ue == pytest.approx(87.0, rel=0.05)


def test_counting_above_a_threshold_drops_the_small_bins() -> None:
    s = spec.build("G1", cycles([(8.0, 100.0), (30.0, 4.0), (60.0, 1.0)]), bin_width_ue=5.0)
    assert s.above(25.0) == pytest.approx(5.0)


def test_counting_above_zero_is_everything() -> None:
    s = spec.build("G1", cycles([(8.0, 100.0), (30.0, 4.0)]), bin_width_ue=5.0)
    assert s.above(0.0) == pytest.approx(s.total_count)


def test_truncation_removes_the_bins_it_says_it_does() -> None:
    s = spec.build("G1", cycles([(8.0, 100.0), (30.0, 4.0), (60.0, 1.0)]), bin_width_ue=5.0)
    cut = s.truncated(25.0)
    assert cut.total_count == pytest.approx(5.0)
    assert cut.largest_range_ue == pytest.approx(s.largest_range_ue)


def test_truncation_raises_the_equivalent_range() -> None:
    s = spec.build("G1", cycles([(8.0, 100.0), (30.0, 4.0), (60.0, 1.0)]), bin_width_ue=5.0)
    assert s.truncated(25.0).equivalent_range_ue() > s.equivalent_range_ue()


def test_a_negative_truncation_threshold_is_refused() -> None:
    s = spec.build("G1", cycles([(8.0, 1.0)]))
    with pytest.raises(RecordError, match="is negative"):
        s.truncated(-1.0)


def test_scaling_multiplies_the_counts_and_not_the_ranges() -> None:
    s = spec.build("G1", cycles([(20.0, 3.0), (40.0, 1.0)]), bin_width_ue=5.0)
    scaled = s.scaled_count(365.0)
    assert scaled.total_count == pytest.approx(s.total_count * 365.0)
    assert scaled.equivalent_range_ue() == pytest.approx(s.equivalent_range_ue())


def test_scaling_by_zero_empties_the_spectrum() -> None:
    s = spec.build("G1", cycles([(20.0, 3.0)]), bin_width_ue=5.0)
    assert s.scaled_count(0.0).total_count == pytest.approx(0.0)


def test_a_negative_scale_factor_is_refused() -> None:
    s = spec.build("G1", cycles([(20.0, 3.0)]))
    with pytest.raises(RecordError, match="is negative"):
        s.scaled_count(-1.0)


def test_merging_adds_the_counts_bin_by_bin() -> None:
    a = spec.build("G1", cycles([(20.0, 3.0)]), bin_width_ue=5.0)
    b = spec.build("G1", cycles([(20.0, 4.0)]), bin_width_ue=5.0)
    assert a.merged_with(b).total_count == pytest.approx(7.0)


def test_merging_keeps_bins_the_other_did_not_have() -> None:
    a = spec.build("G1", cycles([(20.0, 3.0)]), bin_width_ue=5.0)
    b = spec.build("G1", cycles([(70.0, 2.0)]), bin_width_ue=5.0)
    merged = a.merged_with(b)
    assert len(merged) == 2
    assert merged.largest_range_ue == pytest.approx(70.0, rel=0.05)


def test_merging_preserves_the_total_damage() -> None:
    a = spec.build("G1", cycles([(20.0, 3.0), (40.0, 1.0)]), bin_width_ue=5.0)
    b = spec.build("G1", cycles([(20.0, 5.0), (60.0, 2.0)]), bin_width_ue=5.0)
    both = spec.build("G1", cycles([(20.0, 8.0), (40.0, 1.0), (60.0, 2.0)]), bin_width_ue=5.0)
    merged = a.merged_with(b)
    assert merged.equivalent_range_ue() == pytest.approx(both.equivalent_range_ue(), rel=1e-9)


def test_merging_different_bin_widths_is_refused() -> None:
    a = spec.build("G1", cycles([(20.0, 3.0)]), bin_width_ue=5.0)
    b = spec.build("G1", cycles([(20.0, 3.0)]), bin_width_ue=10.0)
    with pytest.raises(RecordError, match="cannot merge"):
        a.merged_with(b)


def test_a_bin_with_no_width_is_refused() -> None:
    with pytest.raises(RecordError, match="is not a width"):
        SpectrumBin(low_ue=0.0, width_ue=0.0, count=1.0, representative_ue=0.0)


def test_a_bin_below_zero_range_is_refused() -> None:
    with pytest.raises(RecordError, match="below zero range"):
        SpectrumBin(low_ue=-5.0, width_ue=5.0, count=1.0, representative_ue=-3.0)


def test_a_negative_bin_count_is_refused() -> None:
    with pytest.raises(RecordError, match="is negative"):
        SpectrumBin(low_ue=0.0, width_ue=5.0, count=-1.0, representative_ue=2.0)


def test_a_representative_outside_its_bin_is_refused() -> None:
    with pytest.raises(RecordError, match="is outside 0.0 to 5.0"):
        SpectrumBin(low_ue=0.0, width_ue=5.0, count=1.0, representative_ue=9.0)


def test_a_spectrum_needs_a_gauge_id() -> None:
    with pytest.raises(RecordError, match="needs a gauge id"):
        Spectrum(" ", 5.0, ())


def test_bins_out_of_order_are_refused() -> None:
    bins = (
        SpectrumBin(10.0, 5.0, 1.0, 12.0),
        SpectrumBin(0.0, 5.0, 1.0, 2.0),
    )
    with pytest.raises(RecordError, match="ascending order"):
        Spectrum("G1", 5.0, bins)


def test_a_spectrum_bin_width_of_zero_is_refused() -> None:
    with pytest.raises(RecordError, match="is not a width"):
        Spectrum("G1", 0.0, ())


def test_building_with_no_width_is_refused() -> None:
    with pytest.raises(RecordError, match="is not a width"):
        spec.build("G1", cycles([(20.0, 1.0)]), bin_width_ue=0.0)


def test_building_with_a_bad_exponent_is_refused() -> None:
    with pytest.raises(RecordError, match="is not positive"):
        spec.build("G1", cycles([(20.0, 1.0)]), exponent=0.0)


def test_a_bad_exponent_on_the_equivalent_range_is_refused() -> None:
    s = spec.build("G1", cycles([(20.0, 1.0)]))
    with pytest.raises(RecordError, match="is not positive"):
        s.equivalent_range_ue(-1.0)
