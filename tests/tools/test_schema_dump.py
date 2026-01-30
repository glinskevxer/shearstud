"""The schema page, read back out of SQLite rather than transcribed."""

from __future__ import annotations

from pathlib import Path

import pytest

from shearstud.tools import schema_dump as dump

pytestmark = pytest.mark.tools


@pytest.fixture
def upgraded(book: Path) -> Path:
    return book


def test_the_shipped_document_is_current() -> None:
    assert dump.DOCUMENT.is_current(dump.body())


def test_the_check_exits_zero_when_the_document_is_current() -> None:
    assert dump.main(["--check"]) == 0


def test_every_table_is_listed(upgraded: Path) -> None:
    names = dump.table_names(upgraded)
    for expected in ("structures", "girders", "details", "gauges", "ratings"):
        assert expected in names


def test_the_internal_tables_are_left_out(upgraded: Path) -> None:
    assert not any(name.startswith("sqlite_") for name in dump.table_names(upgraded))


def test_the_version_table_is_shown(upgraded: Path) -> None:
    assert "schema_version" in dump.table_names(upgraded)


def test_the_columns_of_a_table_come_back(upgraded: Path) -> None:
    columns = {row[0] for row in dump.columns_of(upgraded, "structures")}
    assert "number" in columns
    assert "year_built" in columns


def test_a_primary_key_is_marked(upgraded: Path) -> None:
    rows = {row[0]: row[1] for row in dump.columns_of(upgraded, "structures")}
    assert "primary" in rows["number"]


def test_a_not_null_column_says_no(upgraded: Path) -> None:
    rows = {row[0]: row[2] for row in dump.columns_of(upgraded, "structures")}
    assert rows["name"] == "no"


def test_a_nullable_column_says_yes(upgraded: Path) -> None:
    rows = {row[0]: row[2] for row in dump.columns_of(upgraded, "gauges")}
    assert rows["removed_on"] == "yes"


def test_a_default_is_shown(upgraded: Path) -> None:
    rows = {row[0]: row[3] for row in dump.columns_of(upgraded, "campaigns")}
    assert rows["seasonal_factor"] == "1.0"


def test_the_foreign_keys_of_a_table_come_back(upgraded: Path) -> None:
    keys = dump.foreign_keys_of(upgraded, "girders")
    assert keys
    assert any("structures" in row[1] for row in keys)


def test_a_cascade_is_reported(upgraded: Path) -> None:
    keys = dump.foreign_keys_of(upgraded, "girders")
    assert any(row[2] == "CASCADE" for row in keys)


def test_a_table_with_no_foreign_keys_reports_none(upgraded: Path) -> None:
    assert dump.foreign_keys_of(upgraded, "structures") == []


def test_the_indexes_of_a_table_come_back(upgraded: Path) -> None:
    names = {row[0] for row in dump.indexes_of(upgraded, "girders")}
    assert "girders_by_index" in names


def test_a_unique_index_says_so(upgraded: Path) -> None:
    rows = {row[0]: row[1] for row in dump.indexes_of(upgraded, "girders")}
    assert rows["girders_by_index"] == "yes"


def test_an_index_lists_its_columns(upgraded: Path) -> None:
    rows = {row[0]: row[2] for row in dump.indexes_of(upgraded, "girders")}
    assert "girder_index" in rows["girders_by_index"]


def test_the_internal_indexes_are_left_out(upgraded: Path) -> None:
    for name, _, _ in dump.indexes_of(upgraded, "structures"):
        assert not name.startswith("sqlite_")


def test_the_document_names_the_newest_migration() -> None:
    from shearstud.store import migrate

    assert f"migration {migrate.newest_version()}" in dump.body()


def test_the_document_counts_its_tables() -> None:
    text = dump.body()
    assert " tables: " in text


def test_the_document_names_the_command_that_wrote_it() -> None:
    assert "schema_dump" in dump.DOCUMENT.wrap(dump.body())


def test_building_the_body_leaves_nothing_behind(tmp_path: Path) -> None:
    before = set(tmp_path.iterdir())
    dump.body()
    assert set(tmp_path.iterdir()) == before
