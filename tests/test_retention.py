"""Pruning, and the rule that the newest run is never the one that goes."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from shearstud.errors import StorageError
from shearstud.store import assessment as asm
from shearstud.store import db, retention
from shearstud.store.assessment import StoredRating

pytestmark = pytest.mark.store

TODAY = date(2026, 6, 1)
CUTOFF = date(2014, 1, 1)
NUMBER = "18-SH-0473"


def rating(when: date, number: str = NUMBER, vehicle: str = "TYPE3") -> StoredRating:
    return StoredRating(
        structure_number=number,
        girder_id="G3",
        station_ft=60.0,
        limit_state="strength_i",
        level="operating",
        vehicle=vehicle,
        effect="moment",
        capacity=6000.0,
        factored_dead=1400.0,
        factored_live=3800.0,
        rating_factor=1.2,
        gross_weight_kip=50.0,
        rated_on=when,
    )


def add_second_structure(path: Path) -> None:
    with db.transaction(path) as connection:
        connection.execute(
            "INSERT INTO structures (number, name, county_code, route_class, sequence, "
            "parallel, year_built, span_lengths_ft, continuous, effective_width_rule, "
            "steel_grade, member_condition, redundancy, adtt, lanes_available, "
            "growth_pct_per_yr) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "07-CR-1204",
                "Dry Creek",
                7,
                "CR",
                1204,
                "",
                1954,
                "[62.0]",
                0,
                "legacy",
                "A7",
                "poor",
                "non_redundant",
                80.0,
                2,
                0.5,
            ),
        )


def test_a_cutoff_inside_the_policy_is_refused() -> None:
    with pytest.raises(StorageError, match="inside the 10 year retention policy"):
        retention.check_cutoff(date(2020, 1, 1), TODAY)


def test_a_cutoff_outside_the_policy_is_allowed(seeded_book: Path) -> None:
    # Nothing is raised, and the prune it guards goes through.
    retention.check_cutoff(date(2010, 1, 1), TODAY)
    assert retention.prune_ratings(seeded_book, date(2010, 1, 1), TODAY) == 0


def test_the_policy_boundary_is_where_it_says_it_is() -> None:
    retention.check_cutoff(date(2016, 5, 1), TODAY)
    with pytest.raises(StorageError):
        retention.check_cutoff(date(2016, 7, 1), TODAY)


def test_pruning_removes_the_old_runs(seeded_book: Path) -> None:
    for year in (2005, 2008, 2011, 2020):
        asm.save_rating(seeded_book, rating(date(year, 5, 1)))
    removed = retention.prune_ratings(seeded_book, CUTOFF, TODAY)
    assert removed == 3
    assert len(asm.load_ratings(seeded_book, NUMBER)) == 1


def test_pruning_leaves_the_runs_after_the_cutoff_alone(seeded_book: Path) -> None:
    for year in (2005, 2016, 2020):
        asm.save_rating(seeded_book, rating(date(year, 5, 1)))
    retention.prune_ratings(seeded_book, CUTOFF, TODAY)
    kept = [r.rated_on.year for r in asm.load_ratings(seeded_book, NUMBER)]
    assert kept == [2020, 2016]


def test_a_structure_whose_only_rating_is_old_keeps_it(seeded_book: Path) -> None:
    asm.save_rating(seeded_book, rating(date(1998, 5, 1)))
    removed = retention.prune_ratings(seeded_book, CUTOFF, TODAY)
    assert removed == 0
    assert len(asm.load_ratings(seeded_book, NUMBER)) == 1


def test_the_newest_run_is_kept_per_structure_not_overall(seeded_book: Path) -> None:
    add_second_structure(seeded_book)
    asm.save_rating(seeded_book, rating(date(1998, 5, 1), number="07-CR-1204"))
    asm.save_rating(seeded_book, rating(date(2020, 5, 1)))
    asm.save_rating(seeded_book, rating(date(2005, 5, 1)))
    retention.prune_ratings(seeded_book, CUTOFF, TODAY)
    assert len(asm.load_ratings(seeded_book, "07-CR-1204")) == 1
    assert len(asm.load_ratings(seeded_book, NUMBER)) == 1


def test_a_whole_run_is_kept_not_just_one_row_of_it(seeded_book: Path) -> None:
    asm.save_rating(seeded_book, rating(date(1998, 5, 1), vehicle="TYPE3"))
    asm.save_rating(seeded_book, rating(date(1998, 5, 1), vehicle="TYPE3S2"))
    asm.save_rating(seeded_book, rating(date(1996, 5, 1), vehicle="TYPE3"))
    retention.prune_ratings(seeded_book, CUTOFF, TODAY)
    kept = asm.load_ratings(seeded_book, NUMBER)
    assert len(kept) == 2
    assert {r.vehicle for r in kept} == {"TYPE3", "TYPE3S2"}


def test_pruning_ratings_inside_the_policy_is_refused(seeded_book: Path) -> None:
    with pytest.raises(StorageError, match="retention policy"):
        retention.prune_ratings(seeded_book, date(2022, 1, 1), TODAY)


def test_pruning_an_empty_book_removes_nothing(seeded_book: Path) -> None:
    assert retention.prune_ratings(seeded_book, CUTOFF, TODAY) == 0


def test_pruning_evaluations_keeps_the_newest_per_detail(seeded_book: Path) -> None:
    from shearstud.fatigue.evaluation import Evaluation

    def evaluation(years: float) -> Evaluation:
        return Evaluation(
            detail_id="D07",
            detail_category="E",
            campaign_days=14.0,
            annual_cycles=1000.0,
            effective_range_ksi=4.0,
            largest_range_ksi=9.0,
            infinite_life=False,
            damage_per_first_year=1.0 / years,
            years_remaining=years,
        )

    for year in (2004, 2009, 2012, 2021):
        asm.save_evaluation(seeded_book, evaluation(30.0), "C-2025-04", date(year, 5, 1))
    removed = retention.prune_evaluations(seeded_book, CUTOFF, TODAY)
    assert removed == 3
    assert len(asm.load_evaluations(seeded_book, "D07")) == 1


def test_pruning_evaluations_inside_the_policy_is_refused(seeded_book: Path) -> None:
    with pytest.raises(StorageError, match="retention policy"):
        retention.prune_evaluations(seeded_book, date(2022, 1, 1), TODAY)


def test_pruning_postings_keeps_the_newest_per_structure(seeded_book: Path) -> None:
    from shearstud.rating.posting import PostingDecision, SignLine

    def decision(outcome: str) -> PostingDecision:
        return PostingDecision(
            outcome=outcome,
            lines=(SignLine("single_unit", "TYPE3", 0.8, 20.0),),
            governing_factor=0.8,
        )

    for year, outcome in ((2003, "posted"), (2009, "posted"), (2019, "open")):
        asm.save_posting(seeded_book, NUMBER, decision(outcome), date(year, 5, 1))
    removed = retention.prune_postings(seeded_book, CUTOFF, TODAY)
    assert removed == 2
    assert asm.current_outcome(seeded_book, NUMBER) == "open"


def test_pruning_all_three_reports_each_count(seeded_book: Path) -> None:
    for year in (2005, 2008, 2020):
        asm.save_rating(seeded_book, rating(date(year, 5, 1)))
    report = retention.prune(seeded_book, CUTOFF, TODAY)
    assert report.ratings == 2
    assert report.evaluations == 0
    assert report.postings == 0
    assert report.total == 2
    assert not report.removed_nothing


def test_a_prune_that_removed_nothing_says_so(seeded_book: Path) -> None:
    report = retention.prune(seeded_book, CUTOFF, TODAY)
    assert report.removed_nothing
    assert report.total == 0


def test_a_pruned_book_is_still_consistent(seeded_book: Path) -> None:
    for year in (2005, 2008, 2020):
        asm.save_rating(seeded_book, rating(date(year, 5, 1)))
    retention.prune(seeded_book, CUTOFF, TODAY)
    assert db.foreign_key_violations(seeded_book) == []
    assert db.integrity_check(seeded_book) == []


def test_a_healthy_book_has_no_orphaned_spectra(seeded_book: Path) -> None:
    assert retention.orphaned_spectra(seeded_book) == []


def test_an_orphaned_spectrum_is_found(seeded_book: Path) -> None:
    # Foreign keys are off on this connection on purpose, to make the row the
    # cascade would otherwise have taken.
    with db.connect(seeded_book) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "INSERT INTO spectra (campaign_id, gauge_id, bin_width_ue) VALUES (?, ?, ?)",
            ("C-2025-04", "ghost", 5.0),
        )
        connection.commit()
    assert retention.orphaned_spectra(seeded_book) == [("C-2025-04", "ghost")]


def test_vacuum_leaves_the_book_readable(seeded_book: Path) -> None:
    asm.save_rating(seeded_book, rating(date(2020, 5, 1)))
    retention.vacuum(seeded_book)
    assert len(asm.load_ratings(seeded_book, NUMBER)) == 1
    assert db.integrity_check(seeded_book) == []
