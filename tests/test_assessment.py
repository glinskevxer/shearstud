"""Storing conclusions, which are append only and read newest first."""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import pytest

from shearstud.errors import StorageError
from shearstud.fatigue.evaluation import Evaluation
from shearstud.rating.posting import PostingDecision, SignLine
from shearstud.store import assessment as asm
from shearstud.store import db
from shearstud.store.assessment import StoredRating

pytestmark = pytest.mark.store

NUMBER = "18-SH-0473"


def rating(
    vehicle: str = "TYPE3",
    factor: float = 1.2,
    when: date = date(2025, 6, 1),
    girder_id: str = "G3",
) -> StoredRating:
    return StoredRating(
        structure_number=NUMBER,
        girder_id=girder_id,
        station_ft=60.0,
        limit_state="strength_i",
        level="operating",
        vehicle=vehicle,
        effect="moment",
        capacity=6000.0,
        factored_dead=1400.0,
        factored_live=3800.0,
        rating_factor=factor,
        gross_weight_kip=50.0,
        rated_on=when,
    )


def evaluation(detail_id: str = "D07", years: float = 32.0, infinite: bool = False) -> Evaluation:
    return Evaluation(
        detail_id=detail_id,
        detail_category="E",
        campaign_days=14.0,
        annual_cycles=520000.0,
        effective_range_ksi=4.8,
        largest_range_ksi=11.2,
        infinite_life=infinite,
        damage_per_first_year=0.0 if infinite else 1.0 / years,
        years_remaining=math.inf if infinite else years,
    )


def test_a_rating_round_trips(seeded_book: Path) -> None:
    asm.save_rating(seeded_book, rating())
    loaded = asm.load_ratings(seeded_book, NUMBER)
    assert len(loaded) == 1
    assert loaded[0].vehicle == "TYPE3"
    assert loaded[0].rating_factor == pytest.approx(1.2)
    assert loaded[0].rated_on == date(2025, 6, 1)


def test_a_rating_knows_whether_it_is_adequate() -> None:
    assert rating(factor=1.0).is_adequate
    assert not rating(factor=0.99).is_adequate


def test_a_rating_reports_its_tonnage() -> None:
    assert rating(factor=0.8).tonnage_tons == pytest.approx(0.8 * 50.0 / 2.0)


def test_an_unknown_load_effect_is_refused() -> None:
    with pytest.raises(StorageError, match="unknown load effect"):
        StoredRating(
            structure_number=NUMBER,
            girder_id="G3",
            station_ft=0.0,
            limit_state="strength_i",
            level="operating",
            vehicle="TYPE3",
            effect="torsion",
            capacity=1.0,
            factored_dead=0.0,
            factored_live=1.0,
            rating_factor=1.0,
            gross_weight_kip=50.0,
            rated_on=date(2025, 6, 1),
        )


def test_a_vehicle_with_no_weight_is_refused() -> None:
    with pytest.raises(StorageError, match="is not a weight"):
        StoredRating(
            structure_number=NUMBER,
            girder_id="G3",
            station_ft=0.0,
            limit_state="strength_i",
            level="operating",
            vehicle="TYPE3",
            effect="moment",
            capacity=1.0,
            factored_dead=0.0,
            factored_live=1.0,
            rating_factor=1.0,
            gross_weight_kip=0.0,
            rated_on=date(2025, 6, 1),
        )


def test_ratings_come_back_newest_first(seeded_book: Path) -> None:
    asm.save_rating(seeded_book, rating(when=date(2019, 5, 1)))
    asm.save_rating(seeded_book, rating(when=date(2026, 3, 1)))
    loaded = asm.load_ratings(seeded_book, NUMBER)
    assert [r.rated_on for r in loaded] == [date(2026, 3, 1), date(2019, 5, 1)]


def test_an_older_rating_is_not_overwritten(seeded_book: Path) -> None:
    asm.save_rating(seeded_book, rating(factor=0.7, when=date(2019, 5, 1)))
    asm.save_rating(seeded_book, rating(factor=1.3, when=date(2026, 3, 1)))
    assert len(asm.load_ratings(seeded_book, NUMBER)) == 2


def test_ratings_can_be_narrowed_to_one_run(seeded_book: Path) -> None:
    asm.save_rating(seeded_book, rating(when=date(2019, 5, 1)))
    asm.save_rating(seeded_book, rating(when=date(2026, 3, 1)))
    only = asm.load_ratings(seeded_book, NUMBER, on=date(2019, 5, 1))
    assert len(only) == 1
    assert only[0].rated_on == date(2019, 5, 1)


def test_the_latest_rating_date_is_the_newest_one(seeded_book: Path) -> None:
    asm.save_rating(seeded_book, rating(when=date(2019, 5, 1)))
    asm.save_rating(seeded_book, rating(when=date(2026, 3, 1)))
    assert asm.latest_rating_date(seeded_book, NUMBER) == date(2026, 3, 1)


def test_a_structure_never_rated_has_no_latest_date(seeded_book: Path) -> None:
    assert asm.latest_rating_date(seeded_book, NUMBER) is None


def test_the_governing_rating_comes_from_the_newest_run(seeded_book: Path) -> None:
    asm.save_rating(seeded_book, rating(vehicle="TYPE3", factor=0.4, when=date(2019, 5, 1)))
    asm.save_rating(seeded_book, rating(vehicle="TYPE3", factor=1.5, when=date(2026, 3, 1)))
    asm.save_rating(seeded_book, rating(vehicle="TYPE3S2", factor=1.1, when=date(2026, 3, 1)))
    governing = asm.governing_rating(seeded_book, NUMBER)
    assert governing.rated_on == date(2026, 3, 1)
    assert governing.vehicle == "TYPE3S2"


def test_asking_for_a_governing_rating_that_does_not_exist_is_refused(seeded_book: Path) -> None:
    with pytest.raises(StorageError, match="never been rated"):
        asm.governing_rating(seeded_book, NUMBER)


def test_an_evaluation_round_trips(seeded_book: Path) -> None:
    asm.save_evaluation(seeded_book, evaluation(), "C-2025-04", date(2025, 5, 1))
    history = asm.load_evaluations(seeded_book, "D07")
    assert len(history) == 1
    when, campaign_id, years, infinite = history[0]
    assert when == date(2025, 5, 1)
    assert campaign_id == "C-2025-04"
    assert years == pytest.approx(32.0)
    assert not infinite


def test_an_infinite_life_evaluation_stores_the_sentinel(seeded_book: Path) -> None:
    asm.save_evaluation(seeded_book, evaluation(infinite=True), "C-2025-04", date(2025, 5, 1))
    _, _, years, infinite = asm.load_evaluations(seeded_book, "D07")[0]
    assert infinite
    assert years == pytest.approx(asm.INFINITE_LIFE_YEARS)


def test_evaluations_come_back_newest_first(seeded_book: Path) -> None:
    asm.save_evaluation(seeded_book, evaluation(years=40.0), "C-2025-04", date(2025, 5, 1))
    asm.save_evaluation(seeded_book, evaluation(years=28.0), "C-2025-04", date(2026, 5, 1))
    history = asm.load_evaluations(seeded_book, "D07")
    assert [row[0] for row in history] == [date(2026, 5, 1), date(2025, 5, 1)]


def test_the_shortest_lives_are_the_worst_details(seeded_book: Path) -> None:
    with db.transaction(seeded_book) as connection:
        connection.execute(
            "INSERT INTO details (detail_id, structure_number, girder_id, kind, "
            "category_name, station_ft, fibre) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("D08", NUMBER, "G3", "stiffener_weld", "C", 60.0, "web"),
        )
    asm.save_evaluation(seeded_book, evaluation("D07", years=32.0), "C-2025-04", date(2025, 5, 1))
    asm.save_evaluation(seeded_book, evaluation("D08", years=6.0), "C-2025-04", date(2025, 5, 1))
    worst = asm.shortest_lives(seeded_book)
    assert worst[0][0] == "D08"
    assert worst[0][1] == pytest.approx(6.0)


def test_infinite_life_details_stay_off_the_worst_list(seeded_book: Path) -> None:
    asm.save_evaluation(seeded_book, evaluation(infinite=True), "C-2025-04", date(2025, 5, 1))
    assert asm.shortest_lives(seeded_book) == []


def test_a_list_of_no_details_is_refused(seeded_book: Path) -> None:
    with pytest.raises(StorageError, match="is not a list"):
        asm.shortest_lives(seeded_book, limit=0)


def decision(outcome: str = "posted") -> PostingDecision:
    return PostingDecision(
        outcome=outcome,
        lines=(
            SignLine("single_unit", "TYPE3", 0.82, 20.0),
            SignLine("semi", "TYPE3S2", 1.30, math.inf),
            SignLine("combination", "TYPE3-3", 0.75, 30.0),
        ),
        governing_factor=0.75,
    )


def test_a_posting_round_trips(seeded_book: Path) -> None:
    posting_id = asm.save_posting(seeded_book, NUMBER, decision(), date(2026, 3, 1))
    lines = asm.load_posting_lines(seeded_book, posting_id)
    assert len(lines) == 3
    assert {line.silhouette for line in lines} == {"single_unit", "semi", "combination"}


def test_an_unposted_line_comes_back_unposted(seeded_book: Path) -> None:
    posting_id = asm.save_posting(seeded_book, NUMBER, decision(), date(2026, 3, 1))
    lines = {line.silhouette: line for line in asm.load_posting_lines(seeded_book, posting_id)}
    assert not lines["semi"].is_posted
    assert lines["single_unit"].is_posted
    assert lines["single_unit"].tons == pytest.approx(20.0)


def test_the_current_outcome_is_the_newest_decision(seeded_book: Path) -> None:
    asm.save_posting(seeded_book, NUMBER, decision("posted"), date(2019, 5, 1))
    asm.save_posting(seeded_book, NUMBER, decision("open"), date(2026, 3, 1))
    assert asm.current_outcome(seeded_book, NUMBER) == "open"


def test_a_structure_never_decided_has_no_outcome(seeded_book: Path) -> None:
    assert asm.current_outcome(seeded_book, NUMBER) is None


def test_reading_a_posting_that_is_not_there_is_refused(seeded_book: Path) -> None:
    with pytest.raises(StorageError, match="no posting"):
        asm.load_posting_lines(seeded_book, 999)


def test_deleting_the_structure_takes_the_conclusions_with_it(seeded_book: Path) -> None:
    asm.save_rating(seeded_book, rating())
    asm.save_posting(seeded_book, NUMBER, decision(), date(2026, 3, 1))
    db.execute(seeded_book, "DELETE FROM structures WHERE number = ?", (NUMBER,))
    assert asm.load_ratings(seeded_book, NUMBER) == []
    assert asm.current_outcome(seeded_book, NUMBER) is None
    assert db.foreign_key_violations(seeded_book) == []
