"""Fatigue details, and the loose link between a detail and a gauge."""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.structure import detail as det
from shearstud.structure.detail import FatigueDetail

pytestmark = pytest.mark.fatigue


def make(
    detail_id: str = "G3-D07",
    kind: str = "cover_plate_end",
    category_name: str = "E",
    station_ft: float = 24.5,
    fibre: str = det.FIBRE_BOTTOM,
    gauges: tuple[str, ...] = (),
) -> FatigueDetail:
    return FatigueDetail(
        detail_id=detail_id,
        kind=kind,
        category_name=category_name,
        station_ft=station_ft,
        fibre=fibre,
        gauge_ids=gauges,
    )


def test_a_detail_resolves_its_category() -> None:
    d = make(category_name="E'")
    assert d.detail_category.name == "E'"
    assert d.detail_category.threshold_ksi == pytest.approx(2.6)


def test_a_detail_with_no_gauge_is_not_instrumented() -> None:
    assert not make().is_instrumented


def test_a_detail_with_a_gauge_is() -> None:
    assert make(gauges=("G3-BF-01",)).is_instrumented


def test_a_detail_can_carry_more_than_one_gauge() -> None:
    d = make(gauges=("G3-BF-01", "G3-BF-02"))
    assert len(d.gauge_ids) == 2


def test_listing_the_same_gauge_twice_is_refused() -> None:
    with pytest.raises(InputError, match="listed twice"):
        make(gauges=("G3-BF-01", "G3-BF-01"))


def test_gauges_can_be_replaced_without_touching_the_rest() -> None:
    d = make(gauges=("old",))
    moved = d.with_gauges(["new-a", "new-b"])
    assert moved.gauge_ids == ("new-a", "new-b")
    assert moved.station_ft == pytest.approx(d.station_ft)
    assert moved.category_name == d.category_name


def test_the_default_category_of_each_kind_is_recorded() -> None:
    assert det.default_category("cover_plate_end") == "E"
    assert det.default_category("stiffener_weld") == "C"
    assert det.default_category("base_metal") == "A"


def test_an_unknown_kind_has_no_default() -> None:
    with pytest.raises(InputError, match="unknown detail kind"):
        det.default_category("bolted_splice")


def test_a_detail_at_its_usual_category_is_not_flagged() -> None:
    assert not make(kind="stiffener_weld", category_name="C").is_worse_than_its_kind_suggests


def test_a_detail_downgraded_below_its_kind_is_flagged() -> None:
    downgraded = make(kind="stiffener_weld", category_name="E'")
    assert downgraded.is_worse_than_its_kind_suggests


def test_a_detail_upgraded_above_its_kind_is_not_flagged() -> None:
    upgraded = make(kind="cover_plate_end", category_name="B")
    assert not upgraded.is_worse_than_its_kind_suggests


def test_a_detail_needs_an_id() -> None:
    with pytest.raises(InputError, match="needs an id"):
        make(detail_id=" ")


def test_an_unknown_kind_is_refused_on_the_detail() -> None:
    with pytest.raises(InputError, match="unknown detail kind"):
        make(kind="rivet_head")


def test_an_unknown_fibre_is_refused() -> None:
    with pytest.raises(InputError, match="unknown fibre"):
        make(fibre="soffit")


def test_an_unknown_category_is_refused_through_the_detail() -> None:
    with pytest.raises(InputError, match="unknown detail category"):
        make(category_name="Q")


def test_a_station_behind_the_datum_is_refused() -> None:
    with pytest.raises(InputError, match="behind the datum"):
        make(station_ft=-1.0)


def test_every_fibre_name_is_accepted() -> None:
    for fibre in det.FIBRES:
        assert make(fibre=fibre).fibre == fibre


def test_the_governing_detail_is_the_weakest_one() -> None:
    details = [
        make(detail_id="a", kind="stiffener_weld", category_name="C"),
        make(detail_id="b", kind="cover_plate_end", category_name="E'"),
        make(detail_id="c", kind="groove_weld", category_name="B"),
    ]
    assert det.governing(details).detail_id == "b"


def test_a_tie_on_category_is_broken_by_station() -> None:
    details = [
        make(detail_id="far", category_name="E", station_ft=60.0),
        make(detail_id="near", category_name="E", station_ft=10.0),
    ]
    assert det.governing(details).detail_id == "near"


def test_a_tie_on_station_is_broken_by_id() -> None:
    details = [
        make(detail_id="zulu", category_name="E", station_ft=10.0),
        make(detail_id="alpha", category_name="E", station_ft=10.0),
    ]
    assert det.governing(details).detail_id == "alpha"


def test_choosing_between_nothing_is_refused() -> None:
    with pytest.raises(InputError, match="no details"):
        det.governing([])


def test_instrumented_details_come_back_in_station_order() -> None:
    details = [
        make(detail_id="far", station_ft=80.0, gauges=("g2",)),
        make(detail_id="bare", station_ft=40.0),
        make(detail_id="near", station_ft=10.0, gauges=("g1",)),
    ]
    assert [d.detail_id for d in det.instrumented(details)] == ["near", "far"]


def test_a_girder_with_no_gauges_has_no_instrumented_details() -> None:
    assert det.instrumented([make(), make(detail_id="other")]) == []


def test_one_gauge_can_be_found_on_every_detail_it_watches() -> None:
    details = [
        make(detail_id="weld", station_ft=24.0, gauges=("g1",)),
        make(detail_id="plate", station_ft=24.2, gauges=("g1", "g2")),
        make(detail_id="other", station_ft=70.0, gauges=("g3",)),
    ]
    assert [d.detail_id for d in det.by_gauge(details, "g1")] == ["weld", "plate"]


def test_a_gauge_nobody_listed_watches_nothing() -> None:
    assert det.by_gauge([make(gauges=("g1",))], "g9") == []
