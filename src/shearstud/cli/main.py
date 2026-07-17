"""The command line, which is the only way anyone outside this package uses it.

Every command takes the book of record from one place, ``--book``, defaulting to
a file in the working directory. Nothing here reads an environment variable for
it: a rating office runs several books, one per district, and a command that
silently used the wrong one because a shell had a variable set is a class of
mistake worth being unable to make.

Errors are caught at this boundary and printed. A traceback is right for a
library and wrong for a command, so every ``ShearstudError`` becomes a message
and an exit code, and anything else is left to escape because it is a bug rather
than a condition.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

import click

from shearstud import __version__
from shearstud.errors import InputError, ShearstudError
from shearstud.store import db, migrate

#: Where the book lives when nobody says otherwise.
DEFAULT_BOOK: Final[str] = "shearstud.sqlite3"

#: Exit codes. Anything the user can fix is 1; anything about the book being in
#: the wrong state is 2, so a script can tell a bad argument from a bad book.
EXIT_INPUT: Final[int] = 1
EXIT_STATE: Final[int] = 2


@dataclass(frozen=True, slots=True)
class Context:
    """What every command needs."""

    book: Path

    def require_book(self) -> Path:
        """The book, or a message saying to make one."""
        if not self.book.exists():
            raise click.ClickException(
                f"no book of record at {self.book}. Run 'shearstud init' to make one."
            )
        return self.book


pass_context = click.make_pass_decorator(Context)

#: What a date option looks like when it is right.
DATE_FORMAT: Final[str] = "YYYY-MM-DD"


def parse_date(text: str, what: str) -> date:
    """A date off the command line, or a message a user can act on.

    Eleven commands take a date and every one of them was calling
    ``date.fromisoformat`` directly. That raises ``ValueError``, which is not a
    package error, so it went straight past the error boundary and reached the
    user as a traceback ending in ``Invalid isoformat string``. Naming the
    option in the message is the other half: a command with three date options
    that says one of them is wrong has not said much.
    """
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise InputError(f"{what} {text!r} is not a date, expected {DATE_FORMAT}") from None


def parse_optional_date(text: str | None, what: str) -> date | None:
    """The same, for an option that may be left out."""
    return None if text is None else parse_date(text, what)


class ShearstudGroup(click.Group):
    """A group that turns a package error into a command line error.

    The conversion belongs here rather than in the entry point, because the
    entry point is not what a test drives and not what a subcommand raises
    through. Catching at the top group covers every command under it, since
    click dispatches the whole chain inside this call.
    """

    def invoke(self, ctx: click.Context) -> object:
        """Dispatch the command, translating a package error on the way out."""
        try:
            return super().invoke(ctx)
        except ShearstudError as exc:
            raise click.ClickException(str(exc)) from exc


@click.group(cls=ShearstudGroup)
@click.option(
    "--book",
    type=click.Path(dir_okay=False, path_type=Path),
    default=DEFAULT_BOOK,
    show_default=True,
    help="Path to the book of record.",
)
@click.version_option(__version__, prog_name="shearstud")
@click.pass_context
def main(ctx: click.Context, book: Path) -> None:
    """Fatigue accounting and load rating for steel girder bridges."""
    ctx.obj = Context(book=book)


@main.command()
@pass_context
def init(ctx: Context) -> None:
    """Create the book of record, or bring an existing one up to date."""
    existed = ctx.book.exists()
    applied = migrate.upgrade(ctx.book)
    if not existed:
        click.echo(f"created {ctx.book}")
    if applied:
        click.echo(f"applied migrations {', '.join(str(v) for v in applied)}")
    else:
        click.echo("already up to date")


@main.command()
@pass_context
def status(ctx: Context) -> None:
    """Report the schema version and what the book holds."""
    path = ctx.require_book()
    click.echo(f"book     {path}")
    click.echo(f"schema   {migrate.current_version(path)} of {migrate.newest_version()}")
    pending = migrate.pending(path)
    if pending:
        click.echo(f"pending  {', '.join(str(int(m.VERSION)) for m in pending)}")
    known = db.table_names(path)
    for table in ("structures", "girders", "details", "gauges", "campaigns", "ratings"):
        if table in known:
            click.echo(f"{table:<9}{db.row_count(path, table)}")


@main.command()
@pass_context
def check(ctx: Context) -> None:
    """Run the structural checks SQLite can do on the book itself."""
    path = ctx.require_book()
    problems = db.integrity_check(path)
    violations = db.foreign_key_violations(path)
    for problem in problems:
        click.echo(f"integrity: {problem}", err=True)
    for row in violations:
        click.echo(f"foreign key: {tuple(row)}", err=True)
    if problems or violations:
        raise click.exceptions.Exit(EXIT_STATE)
    click.echo("book: clean")


def run() -> int:
    """Entry point that turns a package error into a message and a code."""
    try:
        main.main(standalone_mode=False)
    except click.ClickException as exc:
        click.echo(f"error: {exc.format_message()}", err=True)
        return EXIT_INPUT
    except click.exceptions.Exit as exc:
        return int(exc.exit_code)
    except click.exceptions.Abort:
        click.echo("aborted", err=True)
        return EXIT_INPUT
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
