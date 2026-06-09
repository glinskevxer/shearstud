"""Commands for the vehicles themselves, and for permitting one across.

The vehicle commands read nothing and write nothing. They exist because the
first question anybody asks when a rating comes back low is which truck did it,
and the second is what that truck looks like, and looking that up in the source
is not an answer you can put in a letter.

The permit command is the opposite: it runs a rating with the permit vehicle and
the permit live load factor, and the factor depends on how the crossing is
controlled. Running it at every control and printing all of them is deliberate.
An engineer deciding whether to escort a load wants both numbers side by side,
and computing only the one they asked for hides the fact that escorting would
have made it issuable.
"""

from __future__ import annotations

import click

from shearstud.analysis import ratingrun as rr
from shearstud.cli.main import Context, main, pass_context
from shearstud.errors import InputError
from shearstud.loads import traverse, vehicles
from shearstud.loads.influence import simple_moment
from shearstud.rating import factors as fac
from shearstud.rating import permit
from shearstud.store import inventory


@main.group()
def vehicle() -> None:
    """The rating vehicles: what is in the fleet and what each one looks like."""


@vehicle.command("list")
@click.option(
    "--class",
    "vehicle_class",
    type=click.Choice(list(vehicles.CLASSES)),
    default=None,
    help="Only one class of vehicle.",
)
@click.option("--sort-weight", is_flag=True, help="Heaviest first instead of by name.")
def list_vehicles(vehicle_class: str | None, sort_weight: bool) -> None:
    """Every vehicle this tool can rate against."""
    names = vehicles.names(vehicle_class)
    trains = [vehicles.vehicle(name) for name in names]
    if sort_weight:
        trains.sort(key=lambda train: -train.gross_kip)
    for train in trains:
        click.echo(
            f"{train.name:<12}{vehicles.vehicle_class(train.name):<10}"
            f"{len(train.axles):>2} axles  {train.gross_kip:>6.1f} kip  "
            f"{train.length_ft:>5.1f} ft"
        )
    click.echo(f"{len(trains)} vehicle(s)")


@vehicle.command("show")
@click.argument("name")
def show_vehicle(name: str) -> None:
    """One vehicle's axles, spacings and running weight."""
    train = vehicles.vehicle(name)
    click.echo(f"name     {train.name}")
    click.echo(f"class    {vehicles.vehicle_class(train.name)}")
    click.echo(f"gross    {train.gross_kip:.1f} kip over {train.length_ft:.1f} ft")
    click.echo(f"heaviest {train.heaviest_axle_kip:.1f} kip")
    # Axles carry the gap to the axle in front, so the distance from the lead
    # axle has to be accumulated. Printing the spacing alone is what a drawing
    # does and is not what somebody placing the vehicle on a span wants.
    running_kip = 0.0
    from_lead_ft = 0.0
    for index, axle in enumerate(train.axles, start=1):
        from_lead_ft += axle.spacing_ft
        running_kip += axle.weight_kip
        click.echo(
            f"  {index:>2}  {from_lead_ft:>6.1f} ft from lead  "
            f"{axle.spacing_ft:>5.1f} ft gap  {axle.weight_kip:>6.1f} kip  "
            f"{running_kip:>6.1f} kip cumulative"
        )


@main.command("permit")
@click.argument("number")
@click.argument("vehicle_name")
@click.option(
    "--kind",
    type=click.Choice(list(permit.KINDS)),
    default=permit.SINGLE_TRIP,
    show_default=True,
    help="Routine authorisation, or one crossing on a known day.",
)
@click.option("--stations", type=int, default=10, show_default=True, help="Stations per span.")
@click.option(
    "--overlay", "overlay_in", type=float, default=0.0, show_default=True, help="Overlay, inches."
)
@pass_context
def permit_command(
    ctx: Context,
    number: str,
    vehicle_name: str,
    kind: str,
    stations: int,
    overlay_in: float,
) -> None:
    """Rate a structure for one permit vehicle, at every level of control."""
    path = ctx.require_book()
    record = inventory.load(path, number)
    policy = inventory.load_policy(path, number)
    train = vehicles.vehicle(vehicle_name)

    # A routine permit crosses unannounced, so escorting it is not a thing the
    # module will build conditions for.
    controls = permit.CONTROLS if kind == permit.SINGLE_TRIP else (permit.MIXED,)
    by_control: dict[str, float] = {}
    for control in controls:
        conditions = permit.PermitConditions(kind=kind, control=control, adtt=policy.adtt)
        settings = rr.settings_for(path, number, overlay_in=overlay_in, stations_per_span=stations)
        results = rr.rate_structure(record, [train], settings, level=fac.OPERATING, legal=True)
        worst = rr.governing(results)
        # The run applies the legal live factor, so the permit factor goes on
        # as a ratio rather than by rating twice.
        scaled = worst.value * fac.legal_live_factor(policy.adtt) / conditions.live_factor
        by_control[control] = scaled
        verdict = "issuable" if permit.is_issuable(scaled) else "REFUSE"
        click.echo(
            f"{control:<10}gamma {conditions.live_factor:.2f}  "
            f"impact {conditions.allowance_frac:.0%}  RF {scaled:.2f}  {verdict}"
        )

    try:
        needed = permit.tightest_control_needed(by_control, kind)
    except InputError:
        # Not an error to report as one. A permit that cannot be issued is an
        # answer, and it is the answer the haulier is waiting for.
        click.echo(f"{vehicle_name} cannot cross {number} under any control this permit allows")
        return
    best = by_control[needed]
    click.echo(
        f"issue as {kind} {needed}, RF {best:.2f}, {permit.margin(best):.0%} margin over the load"
    )


@vehicle.command("envelope")
@click.argument("name")
@click.option("--span-ft", type=float, required=True, help="Simple span to drive it across.")
@click.option("--points", type=int, default=10, show_default=True, help="Stations to report.")
def envelope(name: str, span_ft: float, points: int) -> None:
    """The moment a vehicle puts at each tenth point of a simple span."""
    train = vehicles.vehicle(name)
    if points < 2:
        raise click.BadParameter("a span needs at least two stations")
    click.echo(f"{train.name} on a {span_ft:g} ft simple span")
    for step in range(1, points):
        station_ft = span_ft * step / points
        line = simple_moment(span_ft, station_ft)
        placement = traverse.worst_effect(line, train)
        click.echo(
            f"  {station_ft:>7.1f} ft  {placement.value:>9.1f} kipft  "
            f"lead axle at {placement.lead_position_ft:>6.1f} ft"
        )
    click.echo(f"{train.axle_count} axles, {train.gross_kip:.1f} kip gross")
