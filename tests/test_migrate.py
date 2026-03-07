"""Migrations, and the digest that stops a diverged book being upgraded."""

from __future__ import annotations

from pathlib import Path

import pytest

from shearstud.errors import MigrationError
from shearstud.store import db, migrate
from shearstud.store.migrations import m001_structures, m004_programme

pytestmark = pytest.mark.store


@pytest.fixture
def book(tmp_path: Path) -> Path:
    path = tmp_path / "shearstud.sqlite3"
    migrate.upgrade(path)
    return path


def test_the_migrations_are_a_run_from_one() -> None:
    versions = [int(m.VERSION) for m in migrate.available()]
    assert versions == list(range(1, len(versions) + 1))


def test_every_migration_has_a_name_and_a_body() -> None:
    for m in migrate.available():
        assert str(m.NAME).strip()
        assert "CREATE TABLE" in str(m.UP)


def test_a_fresh_book_has_no_applied_migrations(tmp_path: Path) -> None:
    assert migrate.applied(tmp_path / "nothing.sqlite3") == []
    assert migrate.current_version(tmp_path / "nothing.sqlite3") == 0


def test_upgrading_a_fresh_book_applies_everything(tmp_path: Path) -> None:
    done = migrate.upgrade(tmp_path / "new.sqlite3")
    assert done == [int(m.VERSION) for m in migrate.available()]


def test_an_upgraded_book_is_current(book: Path) -> None:
    assert migrate.is_current(book)
    assert migrate.current_version(book) == migrate.newest_version()
    assert migrate.pending(book) == []


def test_upgrading_twice_does_nothing_the_second_time(book: Path) -> None:
    assert migrate.upgrade(book) == []


def test_the_version_table_records_what_it_ran(book: Path) -> None:
    rows = migrate.applied(book)
    assert [row.version for row in rows] == [1, 2, 3, 4]
    assert [row.name for row in rows] == [
        "structures",
        "measurement",
        "assessment",
        "programme",
    ]
    assert all(len(row.digest) == 64 for row in rows)
    assert all(row.applied_at for row in rows)


def test_the_inventory_tables_are_there(book: Path) -> None:
    names = db.table_names(book)
    for expected in ("structures", "girders", "section_runs", "section_plates", "details"):
        assert expected in names


def test_the_measurement_tables_are_there(book: Path) -> None:
    names = db.table_names(book)
    for expected in ("gauges", "campaigns", "spectra", "spectrum_bins", "thickness_readings"):
        assert expected in names


def test_the_assessment_tables_are_there(book: Path) -> None:
    names = db.table_names(book)
    for expected in ("ratings", "evaluations", "postings", "posting_lines"):
        assert expected in names


def test_a_structure_can_be_written_and_read_back(book: Path) -> None:
    db.execute(
        book,
        "INSERT INTO structures (number, name, county_code, route_class, sequence, "
        "parallel, year_built, span_lengths_ft, continuous, effective_width_rule, "
        "steel_grade, member_condition, redundancy, adtt, lanes_available, "
        "growth_pct_per_yr) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "18-SH-0473",
            "Salt Fork Creek",
            18,
            "SH",
            473,
            "",
            1968,
            "84.0",
            0,
            "tributary",
            "A36",
            "fair",
            "redundant",
            1200.0,
            2,
            2.0,
        ),
    )
    row = db.fetch_one(book, "SELECT name FROM structures WHERE number = ?", ("18-SH-0473",))
    assert row is not None
    assert row["name"] == "Salt Fork Creek"


def test_a_girder_needs_a_structure_to_hang_off(book: Path) -> None:
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            book,
            "INSERT INTO girders (structure_number, girder_id, girder_index, "
            "spacing_left_ft, spacing_right_ft, overhang_ft, slab_thickness_in, "
            "haunch_in, deck_fc_ksi) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("nowhere", "G1", 0, 7.5, 7.5, 0.0, 8.0, 2.0, 4.0),
        )


def test_a_bad_fibre_is_refused_by_the_schema(book: Path) -> None:
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            book,
            "INSERT INTO details (detail_id, structure_number, girder_id, kind, "
            "category_name, station_ft, fibre) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("d1", "s", "g", "cover_plate_end", "E", 10.0, "soffit"),
        )


def test_the_digest_ignores_reformatting() -> None:
    class Reformatted:
        UP = "  ".join(str(m001_structures.UP).split())

    assert migrate.digest_of(m001_structures) == migrate.digest_of(Reformatted)  # type: ignore[arg-type]


def test_the_digest_notices_a_real_change() -> None:
    class Changed:
        UP = str(m001_structures.UP).replace("year_built", "built_year")

    assert migrate.digest_of(m001_structures) != migrate.digest_of(Changed)  # type: ignore[arg-type]


def test_a_book_whose_digest_does_not_match_is_refused(book: Path) -> None:
    db.execute(
        book,
        f"UPDATE {migrate.VERSION_TABLE} SET digest = ? WHERE version = ?",
        ("0" * 64, 2),
    )
    with pytest.raises(MigrationError, match="applied from a different migration"):
        migrate.check_digests(book)


def test_upgrading_a_diverged_book_is_refused(book: Path) -> None:
    db.execute(
        book,
        f"UPDATE {migrate.VERSION_TABLE} SET digest = ? WHERE version = ?",
        ("0" * 64, 1),
    )
    with pytest.raises(MigrationError, match="version 1"):
        migrate.upgrade(book)


def test_a_book_from_the_future_is_refused(book: Path) -> None:
    db.execute(
        book,
        f"INSERT INTO {migrate.VERSION_TABLE} (version, name, digest, applied_at) "
        f"VALUES (?, ?, ?, ?)",
        (99, "from the future", "0" * 64, "2027-01-01T00:00:00+00:00"),
    )
    with pytest.raises(MigrationError, match="the code does not have it"):
        migrate.check_digests(book)


def test_the_newest_version_is_the_last_migration() -> None:
    assert migrate.newest_version() == int(m004_programme.VERSION)


def test_a_partially_upgraded_book_finishes_the_job(tmp_path: Path) -> None:
    path = tmp_path / "partial.sqlite3"
    migrate.upgrade(path)
    db.execute(path, f"DELETE FROM {migrate.VERSION_TABLE} WHERE version > 1")
    assert [int(m.VERSION) for m in migrate.pending(path)] == [2, 3, 4]


def test_an_upgraded_book_has_no_foreign_key_violations(book: Path) -> None:
    assert db.foreign_key_violations(book) == []


def test_an_upgraded_book_passes_the_integrity_check(book: Path) -> None:
    assert db.integrity_check(book) == []


def test_the_programme_table_arrives_with_its_migration(tmp_path: Path) -> None:
    path = tmp_path / "staged.sqlite3"
    migrate.upgrade(path, through=3)
    assert "programme" not in db.table_names(path)
    migrate.upgrade(path)
    assert "programme" in db.table_names(path)


def test_the_programme_table_refuses_a_condition_rating_off_the_scale(book: Path) -> None:
    # The check constraint is on the column, not only in the dataclass, so a
    # row written by anything at all is held to it.
    db.execute(
        book,
        "INSERT INTO structures (number, name, county_code, route_class, sequence, "
        "parallel, year_built, span_lengths_ft, continuous, effective_width_rule, "
        "steel_grade, member_condition, redundancy, adtt, lanes_available, "
        "growth_pct_per_yr) VALUES ('18-SH-0473', 'Salt Fork Creek', 18, 'SH', 473, "
        "'', 1962, '[84.0]', 0, 'tributary', 'A36', 'good', 'redundant', 500, 2, 1.0)",
    )
    with pytest.raises(Exception, match="CHECK constraint"):
        db.execute(
            book,
            "INSERT INTO programme (structure_number, lowest_condition_rating, "
            "daily_traffic, detour_mi, is_posted, last_inspected, updated_on) "
            "VALUES ('18-SH-0473', 11, 100, 1.0, 0, '2025-01-01', '2025-01-02')",
        )


def test_an_upgrade_can_be_stopped_partway(tmp_path: Path) -> None:
    path = tmp_path / "window.sqlite3"
    assert migrate.upgrade(path, through=2) == [1, 2]
    assert migrate.current_version(path) == 2
    assert [int(m.VERSION) for m in migrate.pending(path)] == [3, 4]


def test_a_stopped_upgrade_finishes_when_it_is_run_again(tmp_path: Path) -> None:
    path = tmp_path / "window.sqlite3"
    migrate.upgrade(path, through=2)
    assert migrate.upgrade(path) == [3, 4]
    assert migrate.pending(path) == []


def test_stopping_past_the_end_applies_everything(tmp_path: Path) -> None:
    path = tmp_path / "window.sqlite3"
    assert migrate.upgrade(path, through=99) == [1, 2, 3, 4]


def test_stopping_before_the_first_migration_is_refused(tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="no version 0 to stop at"):
        migrate.upgrade(tmp_path / "window.sqlite3", through=0)
