"""The command line entry point, its book option and its error boundary."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from shearstud import __version__
from shearstud.cli.main import main
from shearstud.store import db, migrate

pytestmark = pytest.mark.cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_the_group_reports_its_version(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_the_help_names_the_domain(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "girder" in result.output.lower()


def test_init_creates_a_book(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "new.sqlite3"
    result = runner.invoke(main, ["--book", str(path), "init"])
    assert result.exit_code == 0
    assert path.exists()
    assert "created" in result.output


def test_init_applies_every_migration(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "new.sqlite3"
    runner.invoke(main, ["--book", str(path), "init"])
    assert migrate.current_version(path) == migrate.newest_version()


def test_init_names_the_migrations_it_applied(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "new.sqlite3"
    result = runner.invoke(main, ["--book", str(path), "init"])
    assert "applied migrations 1, 2, 3" in result.output


def test_init_twice_says_it_is_up_to_date(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "new.sqlite3"
    runner.invoke(main, ["--book", str(path), "init"])
    result = runner.invoke(main, ["--book", str(path), "init"])
    assert result.exit_code == 0
    assert "already up to date" in result.output


def test_status_reports_the_schema_version(runner: CliRunner, book: Path) -> None:
    result = runner.invoke(main, ["--book", str(book), "status"])
    assert result.exit_code == 0
    assert f"schema   {migrate.newest_version()}" in result.output


def test_status_reports_the_book_path(runner: CliRunner, book: Path) -> None:
    result = runner.invoke(main, ["--book", str(book), "status"])
    assert str(book) in result.output


def test_status_counts_the_tables(runner: CliRunner, seeded_book: Path) -> None:
    result = runner.invoke(main, ["--book", str(seeded_book), "status"])
    assert "structures1" in result.output.replace(" ", "")
    assert "details  1" in result.output


def test_status_on_a_missing_book_says_how_to_make_one(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(main, ["--book", str(tmp_path / "gone.sqlite3"), "status"])
    assert result.exit_code != 0
    assert "shearstud init" in result.output


def test_status_names_a_pending_migration(runner: CliRunner, book: Path) -> None:
    # The newest one, read off the code. Naming a number here means the test
    # stops testing anything the day a migration is added after it.
    newest = migrate.newest_version()
    db.execute(book, f"DELETE FROM {migrate.VERSION_TABLE} WHERE version = ?", (newest,))
    result = runner.invoke(main, ["--book", str(book), "status"])
    assert f"pending  {newest}" in result.output


def test_check_passes_on_a_healthy_book(runner: CliRunner, seeded_book: Path) -> None:
    result = runner.invoke(main, ["--book", str(seeded_book), "check"])
    assert result.exit_code == 0
    assert "book: clean" in result.output


def test_check_reports_a_foreign_key_violation(runner: CliRunner, seeded_book: Path) -> None:
    with db.connect(seeded_book) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "INSERT INTO gauges (gauge_id, detail_id, orientation, gauge_factor, "
            "installed_on, channel_limit_ue) VALUES (?, ?, ?, ?, ?, ?)",
            ("ghost", "nowhere", "longitudinal", 2.10, "2025-03-14", 1500.0),
        )
        connection.commit()
    result = runner.invoke(main, ["--book", str(seeded_book), "check"])
    assert result.exit_code == 2
    assert "foreign key" in result.output


def test_check_on_a_missing_book_is_refused(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(main, ["--book", str(tmp_path / "gone.sqlite3"), "check"])
    assert result.exit_code != 0


def test_the_book_defaults_to_the_working_directory(runner: CliRunner) -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["init"])
        assert result.exit_code == 0
        assert Path("shearstud.sqlite3").exists()


def test_an_unknown_command_is_refused(runner: CliRunner) -> None:
    result = runner.invoke(main, ["fly"])
    assert result.exit_code != 0


def test_the_group_class_is_the_one_carrying_the_error_boundary() -> None:
    from shearstud.cli.main import ShearstudGroup

    assert isinstance(main, ShearstudGroup)


def test_the_boundary_lives_on_the_group_and_not_on_the_runner() -> None:
    # The translation from a domain error to a click error has to happen where
    # commands are invoked, or a command called directly in a test raises
    # something a user would never see.
    from shearstud.cli.main import ShearstudGroup

    assert "invoke" in vars(ShearstudGroup)
