"""Gauge installations, and the gauge factor correction that has been needed."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from shearstud.errors import InputError
from shearstud.signals.series import StrainRecord
from shearstud.structure import gauge as gg
from shearstud.structure.gauge import GaugeInstall

pytestmark = pytest.mark.signals

INSTALLED = date(2025, 3, 14)


def install(
    gauge_id: str = "G3-BF-01",
    detail_id: str = "G3-D07",
    orientation: str = gg.ORIENTATION_LONGITUDINAL,
    factor: float = 2.10,
    removed: date | None = None,
) -> GaugeInstall:
    return GaugeInstall(
        gauge_id=gauge_id,
        detail_id=detail_id,
        orientation=orientation,
        gauge_factor=factor,
        installed_on=INSTALLED,
        channel_limit_ue=1500.0,
        removed_on=removed,
    )


def record(samples: list[float]) -> StrainRecord:
    return StrainRecord(
        gauge_id="G3-BF-01",
        started_at=datetime(2025, 4, 1, 8, 0, 0),
        sample_rate_hz=100.0,
        samples_ue=tuple(samples),
    )


def test_a_longitudinal_gauge_reads_bending_stress() -> None:
    assert install().reads_axial_stress


@pytest.mark.parametrize("orientation", [gg.ORIENTATION_TRANSVERSE, gg.ORIENTATION_DIAGONAL])
def test_other_orientations_do_not(orientation: str) -> None:
    assert not install(orientation=orientation).reads_axial_stress


def test_an_unknown_orientation_is_refused() -> None:
    with pytest.raises(InputError, match="unknown orientation"):
        install(orientation="radial")


def test_a_gauge_is_live_between_install_and_removal() -> None:
    g = install(removed=date(2026, 5, 1))
    assert not g.is_live_on(date(2025, 1, 1))
    assert g.is_live_on(INSTALLED)
    assert g.is_live_on(date(2025, 12, 1))
    assert g.is_live_on(date(2026, 5, 1))
    assert not g.is_live_on(date(2026, 6, 1))


def test_a_gauge_never_removed_stays_live() -> None:
    assert install().is_live_on(date(2030, 1, 1))


def test_removing_before_installing_is_refused() -> None:
    with pytest.raises(InputError, match="removed before it was installed"):
        install(removed=date(2024, 1, 1))


def test_days_in_service_counts_from_the_bond_date() -> None:
    assert install().days_in_service_at(date(2025, 3, 24)) == 10


def test_days_in_service_stops_at_removal() -> None:
    g = install(removed=date(2025, 4, 14))
    assert g.days_in_service_at(date(2026, 1, 1)) == 31


def test_asking_before_the_install_date_is_refused() -> None:
    with pytest.raises(InputError, match="before it was installed"):
        install().days_in_service_at(date(2025, 1, 1))


def test_a_new_gauge_is_inside_its_service_life() -> None:
    assert not install().is_past_service_life(date(2026, 1, 1))


def test_an_old_gauge_is_past_it() -> None:
    assert install().is_past_service_life(date(2029, 1, 1))


def test_a_gauge_needs_an_id() -> None:
    with pytest.raises(InputError, match="needs an id"):
        install(gauge_id=" ")


def test_a_gauge_needs_a_detail_to_watch() -> None:
    with pytest.raises(InputError, match="needs a detail to watch"):
        install(detail_id="")


@pytest.mark.parametrize("factor", [1.5, 2.5, 0.0])
def test_a_gauge_factor_far_off_nominal_is_refused(factor: float) -> None:
    with pytest.raises(InputError, match="off the nominal"):
        install(factor=factor)


def test_a_gauge_factor_inside_tolerance_is_accepted() -> None:
    assert install(factor=2.30).gauge_factor == pytest.approx(2.30)


def test_a_channel_with_no_limit_is_refused() -> None:
    with pytest.raises(InputError, match="is not a limit"):
        GaugeInstall(
            gauge_id="g",
            detail_id="d",
            orientation=gg.ORIENTATION_LONGITUDINAL,
            gauge_factor=2.10,
            installed_on=INSTALLED,
            channel_limit_ue=0.0,
        )


def test_a_matching_gauge_factor_leaves_the_record_alone() -> None:
    g = install(factor=2.10)
    r = record([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0])
    assert g.corrected(r, 2.10) is r


def test_a_logger_set_high_produced_readings_that_come_back_up() -> None:
    # The logger divided by 2.142 when the gauge is 2.10, so the readings are
    # low by two percent and the correction multiplies them back.
    g = install(factor=2.10)
    r = record([100.0] * 16)
    fixed = g.corrected(r, 2.142)
    assert fixed.samples_ue[0] == pytest.approx(102.0)


def test_a_logger_set_low_produced_readings_that_come_back_down() -> None:
    g = install(factor=2.10)
    r = record([100.0] * 16)
    fixed = g.corrected(r, 2.058)
    assert fixed.samples_ue[0] == pytest.approx(98.0)


def test_the_correction_keeps_the_gauge_and_the_clock() -> None:
    g = install(factor=2.10)
    r = record([100.0] * 16)
    fixed = g.corrected(r, 2.20)
    assert fixed.gauge_id == r.gauge_id
    assert fixed.started_at == r.started_at


def test_a_logged_factor_of_zero_is_refused() -> None:
    with pytest.raises(InputError, match="is not a factor"):
        install().corrected(record([100.0] * 16), 0.0)


def test_live_gauges_come_back_in_id_order() -> None:
    installs = [
        install(gauge_id="G3-BF-02"),
        install(gauge_id="G3-BF-01"),
        install(gauge_id="G3-BF-09", removed=date(2025, 4, 1)),
    ]
    live = gg.live_on(installs, date(2026, 1, 1))
    assert [g.gauge_id for g in live] == ["G3-BF-01", "G3-BF-02"]


def test_gauges_can_be_found_by_the_detail_they_watch() -> None:
    installs = [
        install(gauge_id="a", detail_id="D1"),
        install(gauge_id="b", detail_id="D2"),
        install(gauge_id="c", detail_id="D1"),
    ]
    assert [g.gauge_id for g in gg.for_detail(installs, "D1")] == ["a", "c"]


def test_axial_only_drops_the_transverse_gauges() -> None:
    installs = [
        install(gauge_id="a"),
        install(gauge_id="b", orientation=gg.ORIENTATION_TRANSVERSE),
        install(gauge_id="c", orientation=gg.ORIENTATION_DIAGONAL),
    ]
    assert [g.gauge_id for g in gg.axial_only(installs)] == ["a"]
