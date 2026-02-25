"""Commands that rate a structure and decide whether to post it.

The rating command prints one line per station and a summary, and it writes
nothing unless asked. That default is deliberate: a rating is a paid piece of
engineering and an accidental one landing in the book of record beside a signed
one is worse than not having it. ``--save`` is the opt in.

The posting command is separate from the rating command even though it needs a
rating, because a posting is a decision and a rating is a calculation. Someone
runs the rating half a dozen times while they are working out what condition
factor to use; they run the posting once.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import click

from shearstud.analysis import ratingrun as rr
from shearstud.analysis.ratingrun import RatingSettings
from shearstud.cli.main import Context, main, pass_context
from shearstud.loads import vehicles
from shearstud.rating import factors as fac
from shearstud.rating import posting as post
from shearstud.store import assessment as asm
from shearstud.store import inventory
from shearstud.store.assessment import StoredRating


def _settings_from(path: Path, number: str, **overrides: object) -> RatingSettings:
    """Build the settings from the structure record, then apply overrides."""
    policy = inventory.load_policy(path, number)
    fields: dict[str, object] = {
        "steel_grade": policy.steel_grade,
        "member_condition": policy.member_condition,
        "redundancy": policy.redundancy,
        "adtt": policy.adtt,
    }
    fields.update({k: v for k, v in overrides.items() if v is not None})
    return RatingSettings(**fields)  # type: ignore[arg-type]


@main.command("rate")
@click.argument("number")
@click.option("--stations", type=int, default=10, show_default=True, help="Stations per span.")
@click.option(
    "--overlay", "overlay_in", type=float, default=0.0, show_default=True, help="Overlay, inches."
)
@click.option(
    "--surface",
    type=click.Choice(["smooth", "minor", "rough"]),
    default="minor",
    show_default=True,
    help="Riding surface, for the dynamic allowance.",
)
@click.option("--condition", default=None, help="Override the recorded member condition.")
@click.option("--design", is_flag=True, help="Rate the design load instead of the legal fleet.")
@click.option("--verbose", is_flag=True, help="Print a line for every station.")
@click.option("--save", is_flag=True, help="Write the results into the book.")
@pass_context
def rate_command(
    ctx: Context,
    number: str,
    stations: int,
    overlay_in: float,
    surface: str,
    condition: str | None,
    design: bool,
    verbose: bool,
    save: bool,
) -> None:
    """Rate a structure against the legal fleet, or against the design load."""
    path = ctx.require_book()
    record = inventory.load(path, number)
    settings = _settings_from(
        path,
        number,
        stations_per_span=stations,
        overlay_in=overlay_in,
        riding_surface=surface,
        member_condition=condition,
    )
    fleet = [vehicles.design_truck()] if design else vehicles.legal_fleet()
    level = fac.INVENTORY if design else fac.OPERATING
    results = rr.rate_structure(record, fleet, settings, legal=not design, level=level)
    if verbose:
        for station in results:
            worst = station.governing
            click.echo(
                f"{station.girder_id:<6}{station.station_ft:>7.1f} ft  "
                f"df {station.distribution_factor:>5.3f}  "
                f"{worst.vehicle:<12}RF {worst.value:>6.2f}"
            )
    worst = rr.governing(results)
    click.echo(f"{number} governing RF {worst.value:.2f} on {worst.vehicle} at {worst.label}")
    click.echo(f"{'adequate' if worst.is_adequate else 'INADEQUATE'} at {level}")
    if not save:
        return
    _save_results(path, number, results, level)
    click.echo(f"saved {len(results)} station ratings")


def _save_results(path: Path, number: str, results: list[rr.StationRating], level: str) -> None:
    today = date.today()
    for station in results:
        for factor in station.ratings:
            asm.save_rating(
                path,
                StoredRating(
                    structure_number=number,
                    girder_id=station.girder_id,
                    station_ft=station.station_ft,
                    limit_state=fac.STRENGTH_I,
                    level=level,
                    vehicle=factor.vehicle,
                    effect="moment",
                    capacity=factor.capacity,
                    factored_dead=factor.factored_dead,
                    factored_live=factor.factored_live,
                    rating_factor=factor.value,
                    gross_weight_kip=factor.gross_weight_kip,
                    rated_on=today,
                ),
            )


@main.command("posting")
@click.argument("number")
@click.option("--stations", type=int, default=10, show_default=True, help="Stations per span.")
@click.option(
    "--overlay", "overlay_in", type=float, default=0.0, show_default=True, help="Overlay, inches."
)
@click.option("--save", is_flag=True, help="Write the decision into the book.")
@pass_context
def posting_command(
    ctx: Context, number: str, stations: int, overlay_in: float, save: bool
) -> None:
    """Work the posting decision from the legal load ratings."""
    path = ctx.require_book()
    record = inventory.load(path, number)
    settings = _settings_from(path, number, stations_per_span=stations, overlay_in=overlay_in)
    by_silhouette = {}
    for silhouette, vehicle_name in post.SIGN_VEHICLES.items():
        train = vehicles.vehicle(vehicle_name)
        results = rr.rate_structure(record, [train], settings)
        by_silhouette[silhouette] = rr.governing(results)
    decision = post.decide(by_silhouette)
    click.echo(f"{number} {decision.outcome} at RF {decision.governing_factor:.2f}")
    for line in post.sign_text(decision):
        click.echo(f"  {line}")
    if decision.outcome == post.OPEN:
        click.echo("  no sign needed")
    if not save:
        return
    asm.save_posting(path, number, decision, date.today())
    click.echo("saved the decision")


@main.command("ratings")
@click.argument("number")
@click.option("--limit", type=int, default=20, show_default=True, help="How many rows.")
@pass_context
def ratings_command(ctx: Context, number: str, limit: int) -> None:
    """What the book already holds for a structure, newest first."""
    path = ctx.require_book()
    rows = asm.load_ratings(path, number)
    if not rows:
        click.echo(f"{number} has never been rated")
        return
    for row in rows[:limit]:
        verdict = "ok" if row.is_adequate else "LOW"
        click.echo(
            f"{row.rated_on}  {row.girder_id:<6}{row.station_ft:>7.1f} ft  "
            f"{row.vehicle:<12}{row.level:<10}RF {row.rating_factor:>6.2f}  {verdict}"
        )
    if len(rows) > limit:
        click.echo(f"... and {len(rows) - limit} more")
