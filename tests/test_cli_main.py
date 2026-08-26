"""The command line entry point, its book option and its error boundary."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from shearstud import __version__
from shearstud.cli.main import main
from shearstud.errors import InputError
from shearstud.store import db, migrate

pytestmark = pytest.mark.cli


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


def test_a_date_reads() -> None:
    from shearstud.cli.main import parse_date

    assert parse_date("2026-04-02", "the reading date") == date(2026, 4, 2)


def test_a_date_that_is_not_a_date_names_the_option() -> None:
    # A command with three date options that says one of them is wrong has
    # not said much.
    from shearstud.cli.main import parse_date

    with pytest.raises(InputError, match="the reading date 'last tuesday' is not a date"):
        parse_date("last tuesday", "the reading date")


def test_a_bad_date_says_what_a_good_one_looks_like() -> None:
    from shearstud.cli.main import DATE_FORMAT, parse_date

    with pytest.raises(InputError, match=DATE_FORMAT):
        parse_date("02/04/2026", "the reading date")


def test_an_optional_date_may_be_left_out() -> None:
    from shearstud.cli.main import parse_optional_date

    assert parse_optional_date(None, "the date") is None
    assert parse_optional_date("2026-04-02", "the date") == date(2026, 4, 2)


def test_a_bad_date_reaches_the_user_as_an_error_and_not_a_traceback(
    runner: CliRunner, seeded_book: Path
) -> None:
    # date.fromisoformat raises ValueError, which is not a package error, so
    # it went straight past the error boundary and out as a traceback.
    result = runner.invoke(
        main, ["--book", str(seeded_book), "report", "overdue", "--on", "last tuesday"]
    )
    assert result.exit_code != 0
    assert "Error:" in result.output
    assert "Traceback" not in result.output
    assert "is not a date" in result.output


def test_every_command_that_takes_a_date_reports_a_bad_one_the_same_way(
    runner: CliRunner, seeded_book: Path
) -> None:
    calls = [
        ["program", "due", "--on", "nope"],
        ["report", "inventory", "--on", "nope"],
        ["book", "prune", "--before", "nope"],
    ]
    for words in calls:
        result = runner.invoke(main, ["--book", str(seeded_book), *words])
        assert result.exit_code != 0, words
        assert "is not a date" in result.output, words
        assert "Traceback" not in result.output, words


def test_about_reports_the_version(runner: CliRunner) -> None:
    result = runner.invoke(main, ["about"])
    assert result.exit_code == 0, result.output
    assert __version__ in result.output


def test_about_reports_the_python_it_is_running_on(runner: CliRunner) -> None:
    import sys

    assert sys.version.split()[0] in runner.invoke(main, ["about"]).output


def test_about_reports_the_schema_this_build_expects(runner: CliRunner) -> None:
    result = runner.invoke(main, ["about"])
    assert f"schema     {migrate.newest_version()} migrations" in result.output


def test_about_names_the_specification_edition(runner: CliRunner) -> None:
    # The second question on any support call about a number, and the answer
    # changes on a different clock from the version.
    from shearstud.cli.main import PROVISIONS

    assert PROVISIONS in runner.invoke(main, ["about"]).output


def test_about_counts_the_catalogue_and_the_fleet(runner: CliRunner) -> None:
    from shearstud.geometry import rolled
    from shearstud.loads import vehicles

    result = runner.invoke(main, ["about"])
    assert f"{len(rolled.designations())} rolled shapes" in result.output
    assert f"{len(vehicles.names())} rating vehicles" in result.output


def test_about_says_where_it_is_installed(runner: CliRunner) -> None:
    assert "shearstud" in runner.invoke(main, ["about"]).output.split("installed")[1]


def test_about_needs_no_book(runner: CliRunner, tmp_path: Path) -> None:
    # It works on an installation nobody has set up yet, which is exactly when
    # somebody is asking what they are running.
    result = runner.invoke(main, ["--book", str(tmp_path / "gone.sqlite3"), "about"])
    assert result.exit_code == 0, result.output


def test_about_appears_in_the_help(runner: CliRunner) -> None:
    assert "about" in runner.invoke(main, ["--help"]).output
