"""Axle trains, and the reversal that has to move the gaps and not the axles."""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.loads.axles import Axle, AxleTrain, train

pytestmark = pytest.mark.loads


def hs20() -> AxleTrain:
    """The design truck: 8, 32, 32 kip at 14 ft and 14 ft."""
    return train("HS20", [8.0, 32.0, 32.0], [14.0, 14.0])


def type3s2() -> AxleTrain:
    """A legal semi, which is deliberately not symmetric."""
    return train("Type 3S2", [10.0, 15.5, 15.5, 15.5, 15.5], [11.0, 4.0, 22.0, 4.0])


def test_a_design_truck_reports_its_weight_and_length() -> None:
    t = hs20()
    assert t.axle_count == 3
    assert t.gross_kip == pytest.approx(72.0)
    assert t.length_ft == pytest.approx(28.0)


def test_axle_offsets_run_from_the_lead_axle() -> None:
    assert hs20().offsets_ft == pytest.approx((0.0, 14.0, 28.0))


def test_weights_come_back_front_to_back() -> None:
    assert type3s2().weights_kip == pytest.approx((10.0, 15.5, 15.5, 15.5, 15.5))


def test_the_heaviest_axle_is_the_one_a_deck_check_uses() -> None:
    assert hs20().heaviest_axle_kip == pytest.approx(32.0)


def test_a_train_iterates_and_counts() -> None:
    t = type3s2()
    assert len(t) == 5
    assert sum(axle.weight_kip for axle in t) == pytest.approx(t.gross_kip)


def test_reversing_keeps_the_weight_and_the_length() -> None:
    t = type3s2()
    back = t.reversed_train()
    assert back.gross_kip == pytest.approx(t.gross_kip)
    assert back.length_ft == pytest.approx(t.length_ft)


def test_reversing_reverses_the_axle_order() -> None:
    back = type3s2().reversed_train()
    assert back.weights_kip == pytest.approx((15.5, 15.5, 15.5, 15.5, 10.0))


def test_reversing_moves_the_gaps_onto_the_right_axles() -> None:
    # Forward gaps are 11, 4, 22, 4. Driven the other way the first gap behind
    # the new lead axle is 4, then 22, then 4, then 11.
    back = type3s2().reversed_train()
    assert [axle.spacing_ft for axle in back] == pytest.approx([0.0, 4.0, 22.0, 4.0, 11.0])


def test_reversing_twice_gives_the_original_geometry() -> None:
    t = type3s2()
    twice = t.reversed_train().reversed_train()
    assert twice.weights_kip == pytest.approx(t.weights_kip)
    assert twice.offsets_ft == pytest.approx(t.offsets_ft)


def test_reversing_a_symmetric_vehicle_changes_nothing_but_the_name() -> None:
    # The design tandem is the only load model here that reads the same either
    # way round. HS20 does not, because its steer axle is light.
    tandem = train("tandem", [25.0, 25.0], [4.0])
    back = tandem.reversed_train()
    assert back.offsets_ft == pytest.approx(tandem.offsets_ft)
    assert back.weights_kip == pytest.approx(tandem.weights_kip)
    assert back.name != tandem.name


def test_reversing_the_design_truck_puts_the_steer_axle_last() -> None:
    assert hs20().reversed_train().weights_kip == pytest.approx((32.0, 32.0, 8.0))


def test_reversing_names_itself() -> None:
    assert hs20().reversed_train().name == "HS20 reversed"


def test_scaling_changes_weight_and_leaves_geometry_alone() -> None:
    t = hs20().scaled(1.25)
    assert t.gross_kip == pytest.approx(90.0)
    assert t.length_ft == pytest.approx(28.0)
    assert t.offsets_ft == pytest.approx((0.0, 14.0, 28.0))


def test_scaling_takes_a_name() -> None:
    assert hs20().scaled(1.25, "permit A").name == "permit A"


def test_scaling_without_a_name_says_what_it_did() -> None:
    assert hs20().scaled(0.75).name == "HS20 at 0.75"


@pytest.mark.parametrize("factor", [0.0, -1.0])
def test_a_scale_factor_that_is_not_positive_is_refused(factor: float) -> None:
    with pytest.raises(InputError, match="not positive"):
        hs20().scaled(factor)


def test_a_lift_axle_carrying_nothing_is_refused() -> None:
    with pytest.raises(InputError, match="is not an axle"):
        Axle(weight_kip=0.0, spacing_ft=4.0)


def test_a_negative_spacing_is_refused() -> None:
    with pytest.raises(InputError, match="is negative"):
        Axle(weight_kip=10.0, spacing_ft=-4.0)


def test_a_lead_axle_that_trails_something_is_refused() -> None:
    with pytest.raises(InputError, match="cannot trail anything"):
        AxleTrain("bad", (Axle(8.0, 3.0), Axle(32.0, 14.0)))


def test_two_axles_on_top_of_each_other_are_refused() -> None:
    with pytest.raises(InputError, match="closer than one axle"):
        train("bad", [8.0, 32.0], [0.5])


def test_the_error_names_the_axle_pair() -> None:
    with pytest.raises(InputError, match="axle 3 is 0.5 ft behind axle 2"):
        train("bad", [8.0, 32.0, 32.0], [14.0, 0.5])


def test_a_train_with_no_axles_is_refused() -> None:
    with pytest.raises(InputError, match="at least one axle"):
        AxleTrain("empty", ())


def test_a_train_needs_a_name() -> None:
    with pytest.raises(InputError, match="needs a name"):
        AxleTrain(" ", (Axle(10.0, 0.0),))


def test_the_builder_counts_the_spacings_it_was_given() -> None:
    with pytest.raises(InputError, match="3 axles need 2 spacings, got 1"):
        train("bad", [8.0, 32.0, 32.0], [14.0])


def test_a_single_axle_vehicle_is_allowed() -> None:
    t = train("one axle", [20.0], [])
    assert t.length_ft == pytest.approx(0.0)
    assert t.gross_kip == pytest.approx(20.0)
