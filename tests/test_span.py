"""Span arrangements, and the global to local conversion that has to be right."""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.structure.span import Span, SpanArrangement, series, simple

pytestmark = pytest.mark.store


def three_span() -> SpanArrangement:
    return series([84.0, 105.0, 84.0], continuous=True)


def test_a_simple_span_has_one_span_and_two_supports() -> None:
    unit = simple(62.5)
    assert unit.span_count == 1
    assert not unit.continuous
    assert unit.support_stations_ft == pytest.approx((0.0, 62.5))
    assert unit.interior_support_stations_ft == ()


def test_a_three_span_unit_reports_its_piers() -> None:
    unit = three_span()
    assert unit.span_count == 3
    assert unit.total_length_ft == pytest.approx(273.0)
    assert unit.interior_support_stations_ft == pytest.approx((84.0, 189.0))


def test_lengths_come_back_in_order() -> None:
    assert three_span().lengths_ft == pytest.approx((84.0, 105.0, 84.0))


def test_a_unit_iterates_its_spans() -> None:
    unit = three_span()
    assert len(unit) == 3
    assert [s.index for s in unit] == [0, 1, 2]


def test_a_typical_arrangement_is_balanced() -> None:
    assert three_span().is_balanced


def test_a_long_middle_span_is_not_balanced() -> None:
    assert not series([60.0, 140.0, 60.0], continuous=True).is_balanced


def test_a_ratio_just_inside_the_limit_is_balanced() -> None:
    assert series([100.0, 134.0], continuous=True).is_balanced


def test_a_ratio_just_outside_the_limit_is_not() -> None:
    assert not series([100.0, 136.0], continuous=True).is_balanced


@pytest.mark.parametrize(
    "station_ft,expected",
    [(0.0, 0), (40.0, 0), (83.9, 0), (84.0, 1), (150.0, 1), (189.0, 2), (273.0, 2)],
)
def test_a_global_station_lands_in_the_right_span(station_ft: float, expected: int) -> None:
    assert three_span().span_index_at(station_ft) == expected


def test_a_pier_station_belongs_to_the_span_that_starts_there() -> None:
    unit = three_span()
    assert unit.span_index_at(83.999) == 0
    assert unit.span_index_at(84.0) == 1


def test_the_far_end_of_the_unit_stays_in_the_last_span() -> None:
    unit = three_span()
    assert unit.span_index_at(unit.total_length_ft) == unit.span_count - 1


def test_global_to_local_and_back_round_trips() -> None:
    unit = three_span()
    for station_ft in (0.0, 12.5, 84.0, 140.25, 189.0, 272.0):
        index, local_ft = unit.to_local(station_ft)
        assert unit.to_global(index, local_ft) == pytest.approx(station_ft)


def test_local_stations_restart_at_every_pier() -> None:
    unit = three_span()
    for station_ft, expected_index in ((84.0, 1), (189.0, 2)):
        index, local_ft = unit.to_local(station_ft)
        assert index == expected_index
        assert local_ft == pytest.approx(0.0)


def test_the_middle_of_the_second_span_is_where_it_should_be() -> None:
    unit = three_span()
    assert unit.to_global(1, 52.5) == pytest.approx(136.5)


def test_a_station_behind_the_unit_is_refused() -> None:
    with pytest.raises(InputError, match="behind the start"):
        three_span().span_index_at(-5.0)


def test_a_station_past_the_unit_is_refused() -> None:
    with pytest.raises(InputError, match="past the end of the unit"):
        three_span().span_index_at(300.0)


def test_a_local_station_past_its_span_is_refused() -> None:
    with pytest.raises(InputError, match="past span 0"):
        three_span().to_global(0, 90.0)


def test_a_negative_local_station_is_refused() -> None:
    with pytest.raises(InputError, match="behind the span"):
        three_span().to_global(1, -1.0)


def test_a_span_index_that_does_not_exist_is_refused() -> None:
    with pytest.raises(InputError, match="no span 3 in a 3 span unit"):
        three_span().to_global(3, 0.0)


def test_a_unit_with_no_spans_is_refused() -> None:
    with pytest.raises(InputError, match="at least one span"):
        SpanArrangement((), continuous=False)


def test_a_single_span_cannot_be_continuous() -> None:
    with pytest.raises(InputError, match="cannot be continuous"):
        series([84.0], continuous=True)


def test_spans_must_carry_their_own_position() -> None:
    with pytest.raises(InputError, match="carries index 5"):
        SpanArrangement((Span(0, 84.0), Span(5, 84.0)), continuous=True)


def test_a_span_shorter_than_a_girder_span_is_refused() -> None:
    with pytest.raises(InputError, match="shorter than a girder span"):
        Span(0, 4.0)


def test_a_negative_span_index_is_refused() -> None:
    with pytest.raises(InputError, match="zero based"):
        Span(-1, 84.0)
