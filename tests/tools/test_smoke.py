"""The end to end run, which says the pieces fit rather than that each is right."""

from __future__ import annotations

from pathlib import Path

import pytest

from shearstud.store import importer
from shearstud.tools import smoke

pytestmark = pytest.mark.tools


def test_the_example_document_is_where_it_says_it_is() -> None:
    assert smoke.EXAMPLE.exists()
    assert smoke.EXAMPLE.name.endswith(".json")


def test_the_example_document_reads() -> None:
    structure = importer.read(smoke.EXAMPLE)
    assert str(structure.number) == "18-SH-0473"
    assert structure.girder_count == 4
    assert len(structure.details()) == 12


def test_the_example_has_a_section_schedule_worth_having() -> None:
    structure = importer.read(smoke.EXAMPLE)
    schedule = structure.girder("G2").schedule
    assert len(schedule) == 3
    assert schedule.section_at(48.0).inertia_in4 > schedule.section_at(6.0).inertia_in4


def test_the_example_has_details_of_more_than_one_category() -> None:
    structure = importer.read(smoke.EXAMPLE)
    categories = {detail.category_name for detail in structure.details()}
    assert len(categories) > 1


def test_the_synthetic_history_has_a_loop_per_truck() -> None:
    history = smoke._strain_history()
    assert len(history) == smoke.SAMPLE_EVENTS * 5 + 1


def test_the_synthetic_history_reaches_the_stated_peak() -> None:
    assert max(smoke._strain_history()) == pytest.approx(smoke.SAMPLE_PEAK_UE)


def test_the_synthetic_history_returns_to_zero() -> None:
    history = smoke._strain_history()
    assert history[0] == 0.0
    assert history[-1] == 0.0


def test_the_run_reports_a_line_per_step(tmp_path: Path) -> None:
    lines = smoke.run(tmp_path / "smoke.sqlite3")
    assert len(lines) == 7
    starts = [line.split()[0] for line in lines]
    assert starts == [
        "schema",
        "inventory",
        "rating",
        "posting",
        "measurement",
        "fatigue",
        "record",
    ]


def test_the_run_rates_every_station_on_every_girder(tmp_path: Path) -> None:
    lines = smoke.run(tmp_path / "smoke.sqlite3")
    rating = next(line for line in lines if line.startswith("rating"))
    # Four girders, nine interior stations each.
    assert "36 stations" in rating


def test_the_run_counts_more_loops_than_trucks(tmp_path: Path) -> None:
    lines = smoke.run(tmp_path / "smoke.sqlite3")
    measurement = next(line for line in lines if line.startswith("measurement"))
    counted = int(measurement.split()[1])
    assert counted > smoke.SAMPLE_EVENTS


def test_the_run_leaves_most_details_unmeasured(tmp_path: Path) -> None:
    # One gauge on twelve details. The point of the line is that it says so.
    lines = smoke.run(tmp_path / "smoke.sqlite3")
    fatigue = next(line for line in lines if line.startswith("fatigue"))
    assert "1 of 12 measured" in fatigue


def test_the_run_leaves_the_book_behind(tmp_path: Path) -> None:
    book = tmp_path / "smoke.sqlite3"
    smoke.run(book)
    assert book.exists()


def test_the_book_the_run_leaves_is_consistent(tmp_path: Path) -> None:
    from shearstud.store import db

    book = tmp_path / "smoke.sqlite3"
    smoke.run(book)
    assert db.foreign_key_violations(book) == []
    assert db.integrity_check(book) == []


def test_the_command_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert smoke.main([]) == 0
    assert "smoke: clean" in capsys.readouterr().out


def test_the_quiet_flag_prints_only_the_verdict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert smoke.main(["--quiet"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert out == ["smoke: clean"]


def test_the_command_leaves_nothing_behind(tmp_path: Path) -> None:
    before = set(tmp_path.iterdir())
    smoke.main(["--quiet"])
    assert set(tmp_path.iterdir()) == before


def test_a_failed_step_is_reported_rather_than_traced(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(book: Path) -> list[str]:
        raise AssertionError("the rating run produced nothing")

    monkeypatch.setattr(smoke, "run", boom)
    assert smoke.main([]) == 1
    assert "smoke: FAILED" in capsys.readouterr().out
