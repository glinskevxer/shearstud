"""Commands that operate on the book itself rather than on what is in it.

Pruning is the only thing this package deletes on purpose, and the command is
built so that the deletion cannot happen by accident. It prints what it would
remove and stops, and it removes nothing until it is told to twice: once with
``--yes`` on the command line, and once by naming a cutoff that is outside the
retention policy, which the store refuses on its own.

That is more friction than a delete usually gets. It is the right amount for a
record somebody may have to produce in a claim.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import click

from shearstud.cli.main import Context, main, parse_date, pass_context
from shearstud.store import db, retention, transfer


@main.group()
def book() -> None:
    """Look after the book of record itself."""


@book.command("prune")
@click.option("--before", required=True, help="Cutoff date, YYYY-MM-DD. Nothing newer is touched.")
@click.option("--yes", is_flag=True, help="Actually remove the rows. Without it, nothing is.")
@click.option("--vacuum", is_flag=True, help="Rebuild the file afterwards to reclaim the space.")
@pass_context
def prune_book(ctx: Context, before: str, yes: bool, vacuum: bool) -> None:
    """Remove superseded conclusions older than a cutoff.

    Each structure keeps its newest rating and posting and each detail keeps
    its newest evaluation, whatever the cutoff says. A structure last rated in
    1998 loses nothing.
    """
    path = ctx.require_book()
    cutoff = parse_date(before, "the cutoff")
    today = date.today()
    retention.check_cutoff(cutoff, today)

    before_counts = {table: db.row_count(path, table) for table in retention.PRUNED_TABLES}
    if not yes:
        click.echo(f"would prune conclusions dated before {cutoff}")
        for table, count in before_counts.items():
            click.echo(f"  {table:<14}{count} row(s) on record")
        click.echo("nothing removed, pass --yes to remove")
        return

    report = retention.prune(path, cutoff, today)
    click.echo(f"ratings      {report.ratings} removed")
    click.echo(f"evaluations  {report.evaluations} removed")
    click.echo(f"postings     {report.postings} removed")
    if report.removed_nothing:
        click.echo("nothing was old enough to remove")
    if vacuum:
        retention.vacuum(path)
        click.echo("rebuilt the file")


@book.command("orphans")
@pass_context
def orphaned(ctx: Context) -> None:
    """Spectra whose gauge is no longer in the book.

    Always empty on a book this package has written, because the foreign key
    cascade takes them. It is worth asking after a restore, which is the one
    route by which they appear.
    """
    path = ctx.require_book()
    rows = retention.orphaned_spectra(path)
    if not rows:
        click.echo("no orphaned spectra")
        return
    for campaign_id, gauge_id in rows:
        click.echo(f"{campaign_id:<14}{gauge_id}")
    click.echo(f"{len(rows)} orphaned spectra, which should not be possible")


@book.command("vacuum")
@pass_context
def vacuum_book(ctx: Context) -> None:
    """Rebuild the file, giving back the space a prune freed."""
    path = ctx.require_book()
    before = path.stat().st_size
    retention.vacuum(path)
    after = path.stat().st_size
    click.echo(f"{before} bytes before, {after} after")


@book.command("counts")
@pass_context
def counts(ctx: Context) -> None:
    """How many rows are in each table."""
    path = ctx.require_book()
    for table in db.table_names(path):
        click.echo(f"{table:<20}{db.row_count(path, table):>8}")


@book.command("export")
@click.argument("target", type=click.Path(dir_okay=False, path_type=Path))
@pass_context
def export_book(ctx: Context, target: Path) -> None:
    """Write the whole book to a transfer file."""
    path = ctx.require_book()
    rows = transfer.write(target, path)
    click.echo(f"wrote {rows} row(s) to {target}")


@book.command("import")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@pass_context
def import_book(ctx: Context, source: Path) -> None:
    """Read a transfer file into an empty book.

    The book has to be empty. Merging two books is a different job with its own
    questions about which copy of a structure wins, and answering those quietly
    inside a load is how one of them disappears.
    """
    path = ctx.require_book()
    document = transfer.read(source)
    written = transfer.load(path, document)
    for table, count in written.items():
        if count:
            click.echo(f"  {table:<20}{count}")
    click.echo(f"read {sum(written.values())} row(s) from {source}")
