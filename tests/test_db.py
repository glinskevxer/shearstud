"""Connection handling, which is where a leak would hide."""

from __future__ import annotations

import gc
import sqlite3
import warnings
from pathlib import Path

import pytest

from shearstud.errors import StorageError
from shearstud.store import db

pytestmark = pytest.mark.store


@pytest.fixture
def book(tmp_path: Path) -> Path:
    path = tmp_path / "shearstud.sqlite3"
    with db.transaction(path) as connection:
        connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE child ("
            "  id INTEGER PRIMARY KEY,"
            "  parent_id INTEGER NOT NULL REFERENCES parent(id),"
            "  value REAL NOT NULL"
            ")"
        )
        connection.execute("INSERT INTO parent (id, name) VALUES (1, 'G3')")
        connection.execute("INSERT INTO child (id, parent_id, value) VALUES (1, 1, 4.5)")
    return path


def test_a_connection_closes_when_the_block_ends(book: Path) -> None:
    with db.connect(book) as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_a_connection_closes_even_when_the_block_raises(book: Path) -> None:
    with pytest.raises(ValueError), db.connect(book) as connection:
        raise ValueError("something went wrong")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_rows_come_back_addressable_by_column_name(book: Path) -> None:
    rows = db.fetch_all(book, "SELECT id, name FROM parent")
    assert rows[0]["name"] == "G3"


def test_foreign_keys_are_on(book: Path) -> None:
    with db.connect(book) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_an_orphan_insert_is_refused(book: Path) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(book, "INSERT INTO child (id, parent_id, value) VALUES (2, 99, 1.0)")


def test_deleting_a_referenced_parent_is_refused(book: Path) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(book, "DELETE FROM parent WHERE id = 1")


def test_a_transaction_commits_on_success(book: Path) -> None:
    with db.transaction(book) as connection:
        connection.execute("INSERT INTO parent (id, name) VALUES (2, 'G4')")
    assert len(db.fetch_all(book, "SELECT id FROM parent")) == 2


def test_a_transaction_rolls_back_on_failure(book: Path) -> None:
    with pytest.raises(RuntimeError), db.transaction(book) as connection:
        connection.execute("INSERT INTO parent (id, name) VALUES (2, 'G4')")
        raise RuntimeError("changed my mind")
    assert len(db.fetch_all(book, "SELECT id FROM parent")) == 1


def test_a_read_only_connection_refuses_a_write(book: Path) -> None:
    with pytest.raises(sqlite3.OperationalError), db.connect(book, read_only=True) as connection:
        connection.execute("INSERT INTO parent (id, name) VALUES (2, 'G4')")


def test_a_read_only_connection_still_reads(book: Path) -> None:
    with db.connect(book, read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM parent").fetchone()[0] == 1


def test_opening_a_missing_book_read_only_is_refused(tmp_path: Path) -> None:
    missing = tmp_path / "gone.sqlite3"
    with (
        pytest.raises(StorageError, match="no book of record"),
        db.connect(missing, read_only=True),
    ):
        pass


def test_opening_a_missing_book_for_writing_creates_it(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "new.sqlite3"
    with db.transaction(path) as connection:
        connection.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    assert path.exists()


def test_fetch_one_finds_a_row(book: Path) -> None:
    row = db.fetch_one(book, "SELECT name FROM parent WHERE id = ?", (1,))
    assert row is not None
    assert row["name"] == "G3"


def test_fetch_one_returns_nothing_when_there_is_nothing(book: Path) -> None:
    assert db.fetch_one(book, "SELECT name FROM parent WHERE id = ?", (99,)) is None


def test_execute_reports_how_many_rows_it_touched(book: Path) -> None:
    touched = db.execute(book, "UPDATE parent SET name = 'G3A' WHERE id = 1")
    assert touched == 1


def test_execute_reports_zero_when_nothing_matched(book: Path) -> None:
    assert db.execute(book, "UPDATE parent SET name = 'x' WHERE id = 99") == 0


def test_execute_many_writes_every_row(book: Path) -> None:
    rows = [(i, f"G{i}") for i in range(10, 20)]
    db.execute_many(book, "INSERT INTO parent (id, name) VALUES (?, ?)", rows)
    assert len(db.fetch_all(book, "SELECT id FROM parent")) == 11


def test_execute_many_with_nothing_to_write_does_nothing(book: Path) -> None:
    assert db.execute_many(book, "INSERT INTO parent (id, name) VALUES (?, ?)", []) == 0


def test_execute_many_is_one_transaction(book: Path) -> None:
    rows = [(10, "ok"), (11, "ok"), (10, "duplicate")]
    with pytest.raises(sqlite3.IntegrityError):
        db.execute_many(book, "INSERT INTO parent (id, name) VALUES (?, ?)", rows)
    assert len(db.fetch_all(book, "SELECT id FROM parent")) == 1


def test_the_table_names_come_back_sorted(book: Path) -> None:
    assert db.table_names(book) == ["child", "parent"]


def test_internal_tables_are_left_out(book: Path) -> None:
    assert not any(name.startswith("sqlite_") for name in db.table_names(book))


def test_a_healthy_book_has_no_foreign_key_violations(book: Path) -> None:
    assert db.foreign_key_violations(book) == []


def test_a_healthy_book_passes_the_integrity_check(book: Path) -> None:
    assert db.integrity_check(book) == []


def test_nothing_is_left_open_after_a_run_of_operations(book: Path) -> None:
    # The filter turns a leaked connection into an error rather than a warning
    # nobody reads, and the row count says the work actually happened.
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        for index in range(30):
            db.execute(book, "INSERT INTO parent (id, name) VALUES (?, ?)", (index + 10, "g"))
            db.fetch_all(book, "SELECT id FROM parent")
        gc.collect()
    assert len(db.fetch_all(book, "SELECT id FROM parent")) == 31
    assert db.integrity_check(book) == []
