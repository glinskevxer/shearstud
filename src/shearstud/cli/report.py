"""Commands that print the two reports the office sends out.

The `--silences` flag prints only the lines that are reporting an absence,
which is the shortest useful summary of a structure this tool can produce: it
is the list of everything nobody has done to it.
"""

from __future__ import annotations

from datetime import date

import click

from shearstud.analysis import report as rep
from shearstud.cli.main import Context, main, pass_context


@main.group()
def report() -> None:
    """Print what the book holds, for one structure or for the district."""


@report.command("structure")
@click.argument("number")
@click.option("--silences", is_flag=True, help="Print only the lines that report an absence.")
@pass_context
def structure_report(ctx: Context, number: str, silences: bool) -> None:
    """Everything on record about one structure, absences included."""
    path = ctx.require_book()
    lines = rep.structure_report(path, number)
    shown = rep.silences(lines) if silences else lines
    if not shown:
        click.echo("nothing missing")
        return
    click.echo(rep.as_text(shown))
    if not silences:
        missing = rep.silences(lines)
        if missing:
            click.echo(f"{len(missing)} of {len(lines)} lines have nothing behind them")


@report.command("inventory")
@click.option("--on", "when", default=None, help="Ask as at a date, YYYY-MM-DD. Default today.")
@pass_context
def inventory_report(ctx: Context, when: str | None) -> None:
    """The district's picture: how much is known, and what is due."""
    path = ctx.require_book()
    today = date.today() if when is None else date.fromisoformat(when)
    click.echo(rep.as_text(rep.inventory_report(path, today)))


@report.command("overdue")
@click.option("--on", "when", default=None, help="Ask as at a date, YYYY-MM-DD. Default today.")
@pass_context
def overdue_report(ctx: Context, when: str | None) -> None:
    """Structures past their inspection date, soonest due first."""
    path = ctx.require_book()
    today = date.today() if when is None else date.fromisoformat(when)
    rows = rep.due_before(path, today)
    if not rows:
        click.echo("nothing overdue")
        return
    for due, number, months in rows:
        click.echo(f"{number:<14}due {due}  on a {months} month interval")
    click.echo(f"{len(rows)} overdue")
