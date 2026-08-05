"""The reports, and the absences they are written to make visible.

The tests here are mostly about what a report says when the book has nothing.
That is the case the format exists for: a report that simply left the line out
would read as "no fatigue problem" rather than "nobody has ever gauged it".
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from shearstud.analysis import report as rep
from shearstud.errors import StorageError
from shearstud.fatigue.evaluation import Evaluation
from shearstud.program import priority
from shearstud.rating import posting
from shearstud.rating.posting import PostingDecision, SignLine
from shearstud.store import assessment as asm
from shearstud.store import db
from shearstud.store import programme as prog
from shearstud.store.assessment import StoredRating
from shearstud.store.programme import ProgrammeRow
from tests import support

pytestmark = pytest.mark.store

NUMBER = "18-SH-0473"
DETAIL = "D07"
CAMPAIGN = "C-2025-04"
TODAY = date(2026, 6, 1)


def open_decision() -> PostingDecision:
    """A structure nobody has to post."""
    return PostingDecision(
        outcome=posting.OPEN,
        lines=(SignLine(silhouette="single", vehicle="TYPE3", rating_factor=1.35, tons=25.0),),
        governing_factor=1.35,
    )


def labelled(lines: list[rep.Line], label: str) -> str:
    return next(line.text for line in lines if line.label == label)


def add_programme(book: Path, rating: int = 8, inspected: date = date(2025, 4, 2)) -> None:
    prog.save(
        book,
        ProgrammeRow(
            structure_number=NUMBER,
            lowest_condition_rating=rating,
            daily_traffic=3400,
            detour_mi=8.5,
            is_posted=False,
            last_inspected=inspected,
            updated_on=inspected,
        ),
    )


def add_rating(book: Path, factor: float = 1.35) -> None:
    asm.save_rating(
        book,
        StoredRating(
            structure_number=NUMBER,
            girder_id="G3",
            station_ft=60.0,
            limit_state="strength_i",
            level="operating",
            vehicle="TYPE3",
            effect="moment",
            capacity=6000.0,
            factored_dead=1400.0,
            factored_live=3800.0,
            rating_factor=factor,
            gross_weight_kip=50.0,
            rated_on=date(2025, 6, 1),
        ),
    )


def add_evaluation(book: Path, years: float = 12.0) -> None:
    asm.save_evaluation(
        book,
        Evaluation(
            detail_id=DETAIL,
            detail_category="E",
            campaign_days=30.0,
            annual_cycles=400000.0,
            effective_range_ksi=6.0,
            largest_range_ksi=9.0,
            infinite_life=False,
            damage_per_first_year=1.0 / years,
            years_remaining=years,
        ),
        CAMPAIGN,
        date(2025, 7, 1),
    )


def test_a_bare_structure_reports_its_identity(seeded_book: Path) -> None:
    lines = rep.structure_report(seeded_book, NUMBER)
    assert labelled(lines, "number") == NUMBER
    assert labelled(lines, "name") == "Salt Fork Creek"


def test_a_bare_structure_says_nobody_has_rated_it(seeded_book: Path) -> None:
    lines = rep.structure_report(seeded_book, NUMBER)
    assert "nobody has rated" in labelled(lines, "rating")


def test_a_bare_structure_says_nobody_has_measured_it(seeded_book: Path) -> None:
    lines = rep.structure_report(seeded_book, NUMBER)
    assert "no detail on this structure has been measured" in labelled(lines, "fatigue")


def test_a_bare_structure_says_nobody_has_inspected_it(seeded_book: Path) -> None:
    lines = rep.structure_report(seeded_book, NUMBER)
    assert "never inspected" in labelled(lines, "inspection")


def test_a_bare_structure_says_there_is_no_posting_decision(seeded_book: Path) -> None:
    lines = rep.structure_report(seeded_book, NUMBER)
    assert "no posting decision" in labelled(lines, "posting")


def test_every_absence_is_a_line_rather_than_a_missing_line(seeded_book: Path) -> None:
    # This is the whole design. Five things are unknown and five lines say so.
    lines = rep.structure_report(seeded_book, NUMBER)
    assert len(rep.silences(lines)) == 5


def test_a_rated_structure_reports_the_governing_factor(seeded_book: Path) -> None:
    add_rating(seeded_book)
    lines = rep.structure_report(seeded_book, NUMBER)
    assert "1.35" in labelled(lines, "rating")
    assert "TYPE3" in labelled(lines, "rating")


def test_a_rated_structure_says_whether_it_carries(seeded_book: Path) -> None:
    add_rating(seeded_book, factor=1.35)
    assert "carries the legal loads" in labelled(
        rep.structure_report(seeded_book, NUMBER), "rating"
    )


def test_a_structure_that_does_not_carry_says_so_in_capitals(seeded_book: Path) -> None:
    add_rating(seeded_book, factor=0.86)
    assert "DOES NOT CARRY" in labelled(rep.structure_report(seeded_book, NUMBER), "rating")


def test_a_measured_structure_reports_the_life_left(seeded_book: Path) -> None:
    add_evaluation(seeded_book, years=12.0)
    assert "12.0 years" in labelled(rep.structure_report(seeded_book, NUMBER), "fatigue")


def test_a_measured_structure_is_not_a_silence(seeded_book: Path) -> None:
    add_evaluation(seeded_book)
    lines = rep.structure_report(seeded_book, NUMBER)
    assert not next(line for line in lines if line.label == "fatigue").is_a_silence


def test_an_inspected_structure_reports_its_interval(seeded_book: Path) -> None:
    add_programme(seeded_book, rating=8)
    lines = rep.structure_report(seeded_book, NUMBER)
    assert "48 months" in labelled(lines, "interval")
    assert "2029" in labelled(lines, "next due")


def test_a_poor_structure_reports_the_short_interval(seeded_book: Path) -> None:
    add_programme(seeded_book, rating=3)
    assert "12 months" in labelled(rep.structure_report(seeded_book, NUMBER), "interval")


def test_a_fully_recorded_structure_has_no_silences(book: Path) -> None:
    # The seeded book carries a girder row with no section runs, so its
    # geometry cannot be loaded and the computed line is a silence. A book
    # with real geometry in it has nothing left to report as missing.
    from shearstud.store import importer, inventory
    from shearstud.tools.walk import REPO_ROOT

    record = importer.read(REPO_ROOT / "examples" / "salt-fork-creek.json")
    inventory.save(book, record)
    detail_id = record.details()[0].detail_id
    db.execute(
        book,
        "INSERT INTO campaigns (campaign_id, structure_number, started_on, ended_on) "
        "VALUES (?, ?, ?, ?)",
        (CAMPAIGN, NUMBER, "2025-04-01", "2025-04-14"),
    )
    add_programme(book)
    add_rating(book)
    asm.save_evaluation(
        book,
        Evaluation(
            detail_id=detail_id,
            detail_category="E",
            campaign_days=30.0,
            annual_cycles=400000.0,
            effective_range_ksi=6.0,
            largest_range_ksi=9.0,
            infinite_life=False,
            damage_per_first_year=1.0 / 12.0,
            years_remaining=12.0,
        ),
        CAMPAIGN,
        date(2025, 7, 1),
    )
    asm.save_posting(book, NUMBER, open_decision(), date(2025, 6, 1))
    assert rep.silences(rep.structure_report(book, NUMBER)) == []


def test_the_computed_line_reports_the_worst_detail(book: Path) -> None:
    from shearstud.store import importer, inventory
    from shearstud.tools.walk import REPO_ROOT

    inventory.save(book, importer.read(REPO_ROOT / "examples" / "salt-fork-creek.json"))
    text = labelled(rep.structure_report(book, NUMBER), "computed")
    assert "ksi at" in text
    assert "from the fatigue truck" in text


def test_the_computed_line_is_separate_from_the_measured_one(book: Path) -> None:
    # Different evidence: one is what crossed the bridge and the other is a
    # truck the specification made up.
    from shearstud.store import importer, inventory
    from shearstud.tools.walk import REPO_ROOT

    inventory.save(book, importer.read(REPO_ROOT / "examples" / "salt-fork-creek.json"))
    lines = rep.structure_report(book, NUMBER)
    labels = [line.label for line in lines]
    assert "fatigue" in labels
    assert "computed" in labels


def test_a_structure_whose_geometry_will_not_load_says_so(seeded_book: Path) -> None:
    assert "the geometry is not in the book" in labelled(
        rep.structure_report(seeded_book, NUMBER), "computed"
    )


def test_a_structure_that_is_not_in_the_book_has_no_report(seeded_book: Path) -> None:
    with pytest.raises(StorageError, match="no structure"):
        rep.structure_report(seeded_book, "99-XX-9999")


def test_a_line_prints_its_label_and_its_text() -> None:
    assert str(rep.Line("rating", "1.35")).startswith("rating")
    assert str(rep.Line("rating", "1.35")).endswith("1.35")


def test_the_labels_line_up() -> None:
    lines = [rep.Line("a", "x"), rep.Line("inspection", "y")]
    assert len({len(str(line).split(" ")[0].ljust(rep.LABEL_WIDTH)) for line in lines}) == 1


def test_a_report_can_be_printed_as_one_block(seeded_book: Path) -> None:
    text = rep.as_text(rep.structure_report(seeded_book, NUMBER))
    assert text.count("\n") == len(rep.structure_report(seeded_book, NUMBER)) - 1


def test_an_empty_inventory_reports_no_structures(book: Path) -> None:
    lines = rep.inventory_report(book, TODAY)
    assert labelled(lines, "structures") == "0"


def test_the_inventory_report_says_how_much_is_ranked(seeded_book: Path) -> None:
    add_programme(seeded_book)
    add_rating(seeded_book)
    assert "1 of 1" in labelled(rep.inventory_report(seeded_book, TODAY), "ranked")


def test_the_inventory_report_names_what_it_could_not_rank(seeded_book: Path) -> None:
    lines = rep.inventory_report(seeded_book, TODAY)
    assert NUMBER in labelled(lines, "not ranked")


def test_the_inventory_report_counts_every_band(seeded_book: Path) -> None:
    add_programme(seeded_book)
    add_rating(seeded_book)
    lines = rep.inventory_report(seeded_book, TODAY)
    for band in priority.BANDS:
        assert labelled(lines, band).split(",")[0].isdigit()


def test_the_inventory_report_says_what_each_band_is_ordered_by(seeded_book: Path) -> None:
    lines = rep.inventory_report(seeded_book, TODAY)
    assert priority.BAND_MEASURE[priority.BAND_RETROFIT] in labelled(lines, priority.BAND_RETROFIT)


def test_the_inventory_report_flags_a_credited_fatigue_life(seeded_book: Path) -> None:
    add_programme(seeded_book)
    add_rating(seeded_book)
    assert "credited" in labelled(rep.inventory_report(seeded_book, TODAY), "unmeasured")


def test_a_recently_inspected_structure_is_not_overdue(seeded_book: Path) -> None:
    add_programme(seeded_book, inspected=date(2026, 4, 1))
    assert rep.due_before(seeded_book, TODAY) == []
    assert labelled(rep.inventory_report(seeded_book, TODAY), "overdue") == "none"


def test_a_structure_past_its_interval_is_overdue(seeded_book: Path) -> None:
    add_programme(seeded_book, inspected=date(2019, 4, 1))
    overdue = rep.due_before(seeded_book, TODAY)
    assert [number for _, number, _ in overdue] == [NUMBER]
    assert labelled(rep.inventory_report(seeded_book, TODAY), "overdue") == "1"


def test_the_overdue_list_carries_the_interval_it_used(seeded_book: Path) -> None:
    add_programme(seeded_book, rating=3, inspected=date(2019, 4, 1))
    assert rep.due_before(seeded_book, TODAY)[0][2] == 12


def test_the_overdue_list_comes_back_soonest_first(seeded_book: Path) -> None:
    db.execute(
        seeded_book,
        support.insert_structure_sql(),
        support.structure_row(
            "07-CR-0112", name="Other", county_code=7, route_class="CR", sequence=112
        ),
    )
    add_programme(seeded_book, inspected=date(2019, 4, 1))
    prog.save(
        seeded_book,
        ProgrammeRow(
            structure_number="07-CR-0112",
            lowest_condition_rating=8,
            daily_traffic=90,
            detour_mi=1.0,
            is_posted=False,
            last_inspected=date(2015, 4, 1),
            updated_on=date(2015, 4, 5),
        ),
    )
    due = rep.due_before(seeded_book, TODAY)
    assert [number for _, number, _ in due] == ["07-CR-0112", NUMBER]
