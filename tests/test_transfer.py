"""Moving a whole book, and the two things a load refuses to do quietly."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from shearstud.errors import StorageError
from shearstud.store import assessment as asm
from shearstud.store import db, migrate, transfer
from shearstud.store import programme as prog
from shearstud.store.assessment import StoredRating
from shearstud.store.programme import ProgrammeRow

pytestmark = pytest.mark.store

NUMBER = "18-SH-0473"


def fill(book: Path) -> None:
    """Put something in every table a transfer carries that the seed misses."""
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
            rating_factor=1.2,
            gross_weight_kip=50.0,
            rated_on=date(2025, 6, 1),
        ),
    )
    prog.save(
        book,
        ProgrammeRow(
            structure_number=NUMBER,
            lowest_condition_rating=7,
            daily_traffic=3400,
            detour_mi=8.5,
            is_posted=False,
            last_inspected=date(2025, 4, 2),
            updated_on=date(2025, 4, 9),
        ),
    )


def test_a_dump_says_what_it_is(seeded_book: Path) -> None:
    document = transfer.dump(seeded_book)
    assert document["format"] == transfer.FORMAT
    assert document["schema_version"] == migrate.newest_version()


def test_a_dump_carries_every_table(seeded_book: Path) -> None:
    assert set(transfer.dump(seeded_book)["tables"]) == set(transfer.TABLES)


def test_a_dump_carries_the_rows(seeded_book: Path) -> None:
    fill(seeded_book)
    document = transfer.dump(seeded_book)
    assert len(document["tables"]["structures"]) == 1
    assert len(document["tables"]["ratings"]) == 1
    assert document["tables"]["structures"][0]["number"] == NUMBER


def test_the_version_table_is_not_carried(seeded_book: Path) -> None:
    # Reading somebody else's copy of it would tell this book a migration ran
    # that never did.
    assert transfer.NOT_CARRIED not in transfer.dump(seeded_book)["tables"]
    assert transfer.NOT_CARRIED not in transfer.TABLES


def test_a_book_with_no_schema_has_nothing_to_move(tmp_path: Path) -> None:
    with pytest.raises(StorageError, match="no schema"):
        transfer.dump(tmp_path / "empty.sqlite3")


def test_a_whole_book_round_trips(seeded_book: Path, tmp_path: Path) -> None:
    fill(seeded_book)
    target = tmp_path / "district.json"
    rows = transfer.write(target, seeded_book)
    assert rows > 0

    fresh = tmp_path / "fresh.sqlite3"
    migrate.upgrade(fresh)
    written = transfer.load(fresh, transfer.read(target))
    assert sum(written.values()) == rows
    for table in transfer.TABLES:
        assert db.row_count(fresh, table) == db.row_count(seeded_book, table), table


def test_the_round_trip_keeps_the_values(seeded_book: Path, tmp_path: Path) -> None:
    fill(seeded_book)
    target = tmp_path / "district.json"
    transfer.write(target, seeded_book)
    fresh = tmp_path / "fresh.sqlite3"
    migrate.upgrade(fresh)
    transfer.load(fresh, transfer.read(target))
    assert asm.load_ratings(fresh, NUMBER)[0].rating_factor == pytest.approx(1.2)
    assert prog.load(fresh, NUMBER).lowest_condition_rating == 7


def test_the_load_reports_what_went_into_each_table(seeded_book: Path, tmp_path: Path) -> None:
    fill(seeded_book)
    document = transfer.dump(seeded_book)
    fresh = tmp_path / "fresh.sqlite3"
    migrate.upgrade(fresh)
    written = transfer.load(fresh, document)
    assert written["structures"] == 1
    assert written["ratings"] == 1
    assert written["spectra"] == 0


def test_a_load_into_a_book_that_is_not_empty_is_refused(seeded_book: Path, tmp_path: Path) -> None:
    # Merging two books is a different job with its own questions about which
    # copy of a structure wins.
    document = transfer.dump(seeded_book)
    with pytest.raises(StorageError, match="already has rows in structures"):
        transfer.load(seeded_book, document)


def test_a_load_at_a_different_schema_is_refused(seeded_book: Path, tmp_path: Path) -> None:
    document = transfer.dump(seeded_book)
    document["schema_version"] = 2
    fresh = tmp_path / "fresh.sqlite3"
    migrate.upgrade(fresh)
    with pytest.raises(StorageError, match="upgrade one of them first"):
        transfer.load(fresh, document)


def test_a_refused_load_leaves_the_book_alone(seeded_book: Path, tmp_path: Path) -> None:
    document = transfer.dump(seeded_book)
    document["schema_version"] = 2
    fresh = tmp_path / "fresh.sqlite3"
    migrate.upgrade(fresh)
    with pytest.raises(StorageError):
        transfer.load(fresh, document)
    assert db.row_count(fresh, "structures") == 0


def test_a_file_that_is_not_one_of_these_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "other.json"
    path.write_text(json.dumps({"format": "something-else"}), encoding="utf-8")
    with pytest.raises(StorageError, match="not a shearstud-book file"):
        transfer.read(path)


def test_a_file_that_is_not_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(StorageError, match="not readable JSON"):
        transfer.read(path)


def test_a_json_file_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(StorageError, match="not a shearstud-book file"):
        transfer.read(path)


def test_a_file_with_no_schema_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"format": transfer.FORMAT, "tables": {}}), encoding="utf-8")
    with pytest.raises(StorageError, match="does not say what schema"):
        transfer.read(path)


def test_a_file_with_no_tables_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "bare.json"
    path.write_text(json.dumps({"format": transfer.FORMAT, "schema_version": 5}), encoding="utf-8")
    with pytest.raises(StorageError, match="carries no tables"):
        transfer.read(path)


def test_a_file_from_a_newer_version_names_the_table_it_carries(tmp_path: Path) -> None:
    path = tmp_path / "newer.json"
    path.write_text(
        json.dumps({"format": transfer.FORMAT, "schema_version": 5, "tables": {"bearings": []}}),
        encoding="utf-8",
    )
    with pytest.raises(StorageError, match="bearings"):
        transfer.read(path)


def test_a_table_nobody_carries_is_refused() -> None:
    with pytest.raises(StorageError, match="not a table this transfer carries"):
        transfer.checked_table("sqlite_master")


def test_every_carried_table_is_a_table(seeded_book: Path) -> None:
    names = set(db.table_names(seeded_book))
    for table in transfer.TABLES:
        assert table in names, table


def test_the_columns_of_a_table_come_off_the_live_schema(seeded_book: Path) -> None:
    columns = transfer.columns_of(seeded_book, "structures")
    assert "number" in columns
    assert "redundancy" in columns


def test_the_columns_of_a_table_nobody_carries_are_refused(seeded_book: Path) -> None:
    with pytest.raises(StorageError, match="not a table this transfer carries"):
        transfer.columns_of(seeded_book, "sqlite_master")


def test_a_document_can_be_counted(seeded_book: Path) -> None:
    fill(seeded_book)
    document = transfer.dump(seeded_book)
    assert transfer.row_count(document) == sum(
        db.row_count(seeded_book, table) for table in transfer.TABLES
    )
