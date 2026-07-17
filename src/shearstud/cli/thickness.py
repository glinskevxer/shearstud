"""Commands for ultrasonic thickness readings and the loss they represent.

Readings go in one at a time, from a field sheet, or a whole sheet at once from
a CSV. The listing reports the loss beside the reading rather than only the
reading, because a remaining thickness means nothing without the nominal one
next to it and looking that up is the step people skip.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import click

from shearstud.cli.main import Context, main, parse_date, pass_context
from shearstud.errors import InputError
from shearstud.geometry import loss
from shearstud.store import inventory
from shearstud.store import thickness as th
from shearstud.store.thickness import StoredReading


@main.group()
def thickness() -> None:
    """Ultrasonic readings, and what they leave of the section."""


@thickness.command("add")
@click.argument("number")
@click.argument("girder_id")
@click.argument("plate_label")
@click.option("--station-ft", type=float, required=True, help="Distance from the near abutment.")
@click.option("--remaining-in", type=float, required=True, help="What the meter read.")
@click.option("--measured", required=True, help="Date of the reading, YYYY-MM-DD.")
@click.option("--note", default="", help="What the inspector wrote beside the number.")
@pass_context
def add_reading(
    ctx: Context,
    number: str,
    girder_id: str,
    plate_label: str,
    station_ft: float,
    remaining_in: float,
    measured: str,
    note: str,
) -> None:
    """Record one reading off a field sheet."""
    path = ctx.require_book()
    th.save(
        path,
        StoredReading(
            structure_number=number,
            girder_id=girder_id,
            plate_label=plate_label,
            station_ft=station_ft,
            remaining_in=remaining_in,
            measured_on=parse_date(measured, "the reading date"),
            note=note,
        ),
    )
    click.echo(f"recorded {plate_label} at {station_ft:g} ft on {girder_id}: {remaining_in:g} in")


@thickness.command("import")
@click.argument("number")
@click.argument("girder_id")
@click.argument("sheet", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--measured", required=True, help="Date of the readings, YYYY-MM-DD.")
@pass_context
def import_sheet(ctx: Context, number: str, girder_id: str, sheet: Path, measured: str) -> None:
    """Read a whole field sheet: plate, station, remaining thickness, note."""
    path = ctx.require_book()
    when = parse_date(measured, "the reading date")
    written = 0
    for reading in _read_sheet(sheet, number, girder_id, when):
        th.save(path, reading)
        written += 1
    click.echo(f"recorded {written} reading(s) on {girder_id} of {number}")


def _read_sheet(sheet: Path, number: str, girder_id: str, when: date) -> list[StoredReading]:
    """A field sheet as readings, refusing anything it cannot parse."""
    out: list[StoredReading] = []
    with sheet.open(encoding="utf-8", newline="") as handle:
        for line_number, row in enumerate(csv.reader(handle), start=1):
            if not any(cell.strip() for cell in row):
                continue
            if len(row) < 3:
                raise InputError(
                    f"{sheet.name} line {line_number}: needs a plate, a station and a thickness"
                )
            try:
                out.append(
                    StoredReading(
                        structure_number=number,
                        girder_id=girder_id,
                        plate_label=row[0].strip(),
                        station_ft=float(row[1]),
                        remaining_in=float(row[2]),
                        measured_on=when,
                        note=row[3].strip() if len(row) > 3 else "",
                    )
                )
            except ValueError:
                if line_number == 1:
                    continue
                raise InputError(
                    f"{sheet.name} line {line_number}: {row[1]!r} and {row[2]!r} are not numbers"
                ) from None
    if not out:
        raise InputError(f"{sheet.name} holds no readings")
    return out


@thickness.command("list")
@click.argument("number")
@click.option("--girder", default=None, help="Only the readings on one girder.")
@click.option("--newest", is_flag=True, help="Only the newest reading at each place.")
@pass_context
def list_readings(ctx: Context, number: str, girder: str | None, newest: bool) -> None:
    """Every reading on a structure, newest first."""
    path = ctx.require_book()
    rows = th.load(path, number, girder)
    if newest:
        rows = th.newest_per_location(rows)
    if not rows:
        click.echo("no readings")
        return
    for row in rows:
        note = f"  {row.note}" if row.note else ""
        click.echo(
            f"{row.measured_on}  {row.girder_id:<6}{row.plate_label:<10}"
            f"{row.station_ft:>7.1f} ft  {row.remaining_in:>6.3f} in{note}"
        )
    click.echo(f"{len(rows)} reading(s) on {len(th.locations(rows))} location(s)")


@thickness.command("loss")
@click.argument("number")
@click.argument("girder_id")
@pass_context
def show_loss(ctx: Context, number: str, girder_id: str) -> None:
    """What the readings leave of each plate, worst first."""
    path = ctx.require_book()
    record = inventory.load(path, number)
    girder = record.girder(girder_id)
    rows = th.newest_per_location(th.load(path, number, girder_id))
    if not rows:
        click.echo(f"no readings on {girder_id}")
        return
    for run in girder.schedule:
        on_run = [r for r in rows if run.from_station_ft <= r.station_ft <= run.to_station_ft]
        if not on_run:
            continue
        click.echo(f"{run.from_station_ft:g} to {run.to_station_ft:g} ft")
        for finding in loss.findings(run.section, [r.as_reading() for r in on_run]):
            verdict = "severe" if finding.is_severe else "finding" if finding.is_finding else "note"
            click.echo(
                f"  {finding.plate_label:<10}{finding.nominal_in:>6.3f} nominal  "
                f"{finding.loss_in:>6.3f} lost  {finding.loss_frac:>6.1%}  {verdict}"
            )
        remaining = loss.remaining_capacity_frac(run.section, [r.as_reading() for r in on_run])
        click.echo(f"  bottom fibre section modulus at {remaining:.1%} of nominal")


@thickness.command("rate")
@click.argument("number")
@click.option("--girder", default=None, help="Only one girder.")
@pass_context
def corrosion_rate(ctx: Context, number: str, girder: str | None) -> None:
    """Loss per year at each place that has been measured twice."""
    path = ctx.require_book()
    grouped = th.locations(th.load(path, number, girder))
    if not grouped:
        click.echo("no readings")
        return
    reported = 0
    for group in grouped:
        rate = th.corrosion_rate_in_per_yr(group)
        if rate is None:
            continue
        first = min(group, key=lambda r: r.measured_on)
        click.echo(
            f"{first.girder_id:<6}{first.plate_label:<10}{first.station_ft:>7.1f} ft  "
            f"{rate:>8.4f} in/yr over {len(group)} reading(s)"
        )
        reported += 1
    if reported == 0:
        click.echo(f"{len(grouped)} location(s), none measured more than once")
