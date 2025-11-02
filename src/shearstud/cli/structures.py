"""Commands for the inventory: what is on the books and what it looks like.

Output is columns of plain text, aligned, no borders. That is what pipes into
awk on the district engineer's machine, and it is what a rating office has
always got out of this kind of tool. Anything that wants structure gets the
JSON document instead, through ``structure export``.
"""

from __future__ import annotations

from pathlib import Path

import click

from shearstud.cli.main import Context, main, pass_context
from shearstud.store import importer, inventory
from shearstud.store.inventory import StructurePolicy


@main.group()
def structure() -> None:
    """Look at and change the inventory."""


@structure.command("list")
@pass_context
def list_structures(ctx: Context) -> None:
    """Every structure in the book, in file cabinet order."""
    path = ctx.require_book()
    numbers = inventory.numbers(path)
    if not numbers:
        click.echo("no structures")
        return
    for number in numbers:
        record = inventory.load(path, number)
        click.echo(
            f"{number:<14}{record.girder_count:>3} girders  "
            f"{record.length_ft:>7.1f} ft  {record.name}"
        )


@structure.command("show")
@click.argument("number")
@click.option("--girders/--no-girders", default=True, help="List the girders too.")
@pass_context
def show_structure(ctx: Context, number: str, girders: bool) -> None:
    """Everything the book holds about one structure."""
    path = ctx.require_book()
    record = inventory.load(path, number)
    click.echo(f"number   {record.number}")
    click.echo(f"name     {record.name}")
    click.echo(f"built    {record.year_built or 'not recorded'}")
    click.echo(f"spans    {', '.join(f'{v:g}' for v in record.spans.lengths_ft)} ft")
    click.echo(f"joined   {'continuous' if record.spans.continuous else 'simple'}")
    click.echo(f"width    {record.effective_width_rule} rule")
    click.echo(f"details  {len(record.details())}")
    if not girders:
        return
    for girder in record.girders:
        kind = "exterior" if girder.is_exterior else "interior"
        click.echo(
            f"  {girder.girder_id:<8}{kind:<10}{len(girder.schedule):>2} runs  "
            f"{len(girder.details):>2} details"
        )


@structure.command("import")
@click.argument("document", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--grade", default="A36", show_default=True, help="Steel grade.")
@click.option("--condition", default="good", show_default=True, help="Member condition.")
@click.option("--redundancy", default="redundant", show_default=True, help="System redundancy.")
@click.option("--adtt", type=float, default=0.0, show_default=True, help="Truck traffic a day.")
@click.option("--lanes", type=int, default=2, show_default=True, help="Lanes open to trucks.")
@click.option("--growth", type=float, default=0.0, show_default=True, help="Traffic growth, %/yr.")
@click.option("--force", is_flag=True, help="Replace a structure that is already there.")
@pass_context
def import_structure(
    ctx: Context,
    document: Path,
    grade: str,
    condition: str,
    redundancy: str,
    adtt: float,
    lanes: int,
    growth: float,
    force: bool,
) -> None:
    """Read a structure document into the book."""
    path = ctx.require_book()
    record = importer.read(document)
    number = str(record.number)
    if inventory.exists(path, number) and not force:
        raise click.ClickException(f"{number} is already in the book. Use --force to replace it.")
    policy = StructurePolicy(
        steel_grade=grade,
        member_condition=condition,
        redundancy=redundancy,
        adtt=adtt,
        lanes_available=lanes,
        growth_pct_per_yr=growth,
    )
    inventory.save(path, record, policy)
    click.echo(f"imported {number} with {record.girder_count} girders")


@structure.command("export")
@click.argument("number")
@click.argument("document", type=click.Path(dir_okay=False, path_type=Path))
@pass_context
def export_structure(ctx: Context, number: str, document: Path) -> None:
    """Write a structure back out as a document."""
    path = ctx.require_book()
    record = inventory.load(path, number)
    importer.write(document, record)
    click.echo(f"wrote {document}")


@structure.command("delete")
@click.argument("number")
@click.option("--yes", is_flag=True, help="Do not ask.")
@pass_context
def delete_structure(ctx: Context, number: str, yes: bool) -> None:
    """Remove a structure and everything hanging off it."""
    path = ctx.require_book()
    if not inventory.exists(path, number):
        raise click.ClickException(f"no structure {number} in the book")
    if not yes:
        click.confirm(f"delete {number} and every rating, gauge and reading on it?", abort=True)
    inventory.delete(path, number)
    click.echo(f"deleted {number}")


@structure.command("details")
@click.argument("number")
@click.option("--worst-first", is_flag=True, help="Order by category rather than station.")
@pass_context
def list_details(ctx: Context, number: str, worst_first: bool) -> None:
    """Every fatigue detail on a structure."""
    path = ctx.require_book()
    record = inventory.load(path, number)
    rows = []
    for girder in record.girders:
        for detail in girder.details:
            rows.append((girder.girder_id, detail))
    if not rows:
        click.echo("no details")
        return
    if worst_first:
        rows.sort(key=lambda r: (r[1].detail_category.constant_a, r[1].station_ft))
    for girder_id, detail in rows:
        flag = " downgraded" if detail.is_worse_than_its_kind_suggests else ""
        click.echo(
            f"{detail.detail_id:<12}{girder_id:<6}{detail.station_ft:>7.1f} ft  "
            f"{detail.category_name:<3}{detail.fibre:<8}{detail.kind}{flag}"
        )
