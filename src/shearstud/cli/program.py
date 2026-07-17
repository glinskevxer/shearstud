"""Commands for the inspection programme: what gets visited, and when.

The worklist command prints the gaps before the ranking. That is deliberate and
it is the opposite of what looks good in a demonstration. A worklist that opens
with forty ranked structures reads as a complete picture of the inventory, and
the eleven that could not be ranked are the ones nobody has looked at. Putting
them first makes the list uncomfortable to read, which is the correct amount of
comfortable.
"""

from __future__ import annotations

from datetime import date

import click

from shearstud.analysis import programrun as pr
from shearstud.cli.main import Context, main, parse_date, parse_optional_date, pass_context
from shearstud.program import interval, priority
from shearstud.store import programme as prog
from shearstud.store.programme import ProgrammeRow


@main.group()
def program() -> None:
    """The inspection programme: intervals, priority and the worklist."""


@program.command("record")
@click.argument("number")
@click.option(
    "--condition",
    type=click.IntRange(interval.MIN_CONDITION_RATING, interval.MAX_CONDITION_RATING),
    required=True,
    help="Lowest component condition rating from the inspection.",
)
@click.option("--inspected", required=True, help="Date of the inspection, YYYY-MM-DD.")
@click.option("--traffic", type=int, default=0, show_default=True, help="Vehicles a day.")
@click.option(
    "--detour-mi",
    type=float,
    default=0.0,
    show_default=True,
    help="Miles of detour if the structure closes.",
)
@click.option("--posted/--not-posted", default=False, help="Whether a weight limit is up.")
@pass_context
def record_inspection(
    ctx: Context,
    number: str,
    condition: int,
    inspected: str,
    traffic: int,
    detour_mi: float,
    posted: bool,
) -> None:
    """Write down what an inspection found."""
    path = ctx.require_book()
    prog.save(
        path,
        ProgrammeRow(
            structure_number=number,
            lowest_condition_rating=condition,
            daily_traffic=traffic,
            detour_mi=detour_mi,
            is_posted=posted,
            last_inspected=parse_date(inspected, "the inspection date"),
            updated_on=date.today(),
        ),
    )
    click.echo(f"recorded {number} at condition {condition}, inspected {inspected}")


@program.command("show")
@click.argument("number")
@pass_context
def show_programme(ctx: Context, number: str) -> None:
    """What the programme currently believes about one structure."""
    path = ctx.require_book()
    row = prog.load(path, number)
    life_years, measured = pr.credited_life_years(path, number)
    state = row.state(life_years)
    decision = interval.decide(state)
    click.echo(f"number     {row.structure_number}")
    click.echo(f"condition  {row.lowest_condition_rating}")
    click.echo(f"posted     {'yes' if row.is_posted else 'no'}")
    click.echo(f"traffic    {row.daily_traffic} a day over {row.detour_mi:g} miles of detour")
    click.echo(f"inspected  {row.last_inspected}")
    source = "measured" if measured else "no measurement, credited"
    click.echo(f"life       {life_years:.1f} years ({source})")
    click.echo(f"interval   {decision.months} months, {decision.reason}")
    click.echo(f"next due   {decision.next_due(row.last_inspected)}")


@program.command("worklist")
@click.option("--limit", type=int, default=0, help="Print only the first few ranked structures.")
@click.option("--band", default=None, help="Only one band, by name.")
@pass_context
def show_worklist(ctx: Context, limit: int, band: str | None) -> None:
    """The office's list, gaps first."""
    path = ctx.require_book()
    result = pr.build(path)

    for reason in pr.GAP_REASONS:
        missing = result.gaps_for(reason)
        if missing:
            click.echo(f"not ranked ({reason}): {', '.join(missing)}")
    if result.unmeasured:
        click.echo(f"ranked on a credited life: {', '.join(result.unmeasured)}")

    ranked = list(result.ranked)
    if band is not None:
        ranked = priority.in_band(ranked, band)
    if limit > 0:
        ranked = ranked[:limit]
    if not ranked:
        click.echo("nothing ranked")
        return
    for candidate in ranked:
        click.echo(
            f"{candidate.number:<14}{priority.band_of(candidate):<12}"
            f"{priority.reason_for(candidate)}"
        )
    click.echo(
        f"{len(result.ranked)} of {result.structure_count} structures ranked "
        f"({result.ranked_frac:.0%})"
    )


@program.command("due")
@click.option("--on", "when", default=None, help="Ask as at a date, YYYY-MM-DD. Default today.")
@pass_context
def show_due(ctx: Context, when: str | None) -> None:
    """Structures whose inspection date has gone past."""
    path = ctx.require_book()
    today = parse_optional_date(when, "the date to ask as at") or date.today()
    overdue: list[tuple[date, str, int]] = []
    for row in prog.load_all(path):
        life_years, _ = pr.credited_life_years(path, row.structure_number)
        decision = interval.decide(row.state(life_years))
        if decision.is_overdue(row.last_inspected, today):
            overdue.append(
                (decision.next_due(row.last_inspected), row.structure_number, decision.months)
            )
    if not overdue:
        click.echo("nothing overdue")
        return
    for due, number, months in sorted(overdue):
        click.echo(f"{number:<14}due {due}  on a {months} month interval")
    click.echo(f"{len(overdue)} overdue")
