"""Commands for the shear connectors, which are what make composite action true.

Two checks, printed together and labelled, because they answer different
questions and the answers are in different units. Fatigue decides how far apart
the rows go and comes back in inches. Strength decides how many rows there are
between maximum moment and zero moment and comes back as a count. Reporting one
of them as "the stud design" is how a girder ends up with the right total number
of studs at the wrong spacing, which loses composite action gradually and shows
nothing on the outside of the deck.

The shear range the fatigue check needs is the live load shear range at the
section, which this takes from a shear run rather than from a number typed on
the command line. A stud spacing worked out from a shear range somebody
remembered is a stud spacing nobody can reproduce.
"""

from __future__ import annotations

import click

from shearstud.analysis import shearrun as sr
from shearstud.analysis.ratingrun import RatingSettings
from shearstud.cli.main import Context, main, pass_context
from shearstud.loads import vehicles
from shearstud.rating import studs
from shearstud.rating.studs import StudSpec
from shearstud.store import inventory


@main.command("studs")
@click.argument("number")
@click.argument("girder_id")
@click.option(
    "--diameter-in",
    type=float,
    default=0.875,
    show_default=True,
    help="Stud diameter. The standard sizes are 5/8, 3/4, 7/8 and 1 inch.",
)
@click.option(
    "--height-in", type=float, default=5.0, show_default=True, help="Stud height after welding."
)
@click.option(
    "--strength-ksi",
    type=float,
    default=60.0,
    show_default=True,
    help="Stud tensile strength.",
)
@click.option("--per-row", type=int, default=3, show_default=True, help="Studs across the flange.")
@click.option(
    "--cycles",
    type=float,
    default=None,
    help="Design cycles. Omit for the infinite life resistance.",
)
@click.option("--stations", type=int, default=10, show_default=True, help="Stations per span.")
@pass_context
def stud_command(
    ctx: Context,
    number: str,
    girder_id: str,
    diameter_in: float,
    height_in: float,
    strength_ksi: float,
    per_row: int,
    cycles: float | None,
    stations: int,
) -> None:
    """Stud spacing from fatigue, and stud count from strength."""
    path = ctx.require_book()
    record = inventory.load(path, number)
    policy = inventory.load_policy(path, number)
    girder = record.girder(girder_id)
    spec = StudSpec(diameter_in=diameter_in, height_in=height_in, tensile_strength_ksi=strength_ksi)

    click.echo(f"stud     {spec.diameter_in:g} in by {spec.height_in:g} in, {per_row} per row")
    if not spec.is_standard:
        click.echo(f"stud     {spec.diameter_in:g} in is not a standard diameter")
    low_in, high_in = studs.pitch_limits_in(spec)
    click.echo(f"limits   pitch between {low_in:.2f} and {high_in:.2f} in")

    settings = RatingSettings(
        steel_grade=policy.steel_grade,
        member_condition=policy.member_condition,
        redundancy=policy.redundancy,
        adtt=policy.adtt,
        stations_per_span=stations,
    )
    results = [
        station
        for station in sr.rate_structure(record, vehicles.legal_fleet(), settings)
        if station.girder_id == girder_id
    ]
    if not results:
        click.echo(f"nothing rated on {girder_id}")
        return

    governing_pitch_in = high_in
    at_station_ft = 0.0
    for station in results:
        composite = girder.composite_at(station.station_ft)
        # The live load shear range at the section. A truck crossing takes the
        # shear from its largest positive value to its largest negative one,
        # and the studs see the difference.
        shear_range_kip = max(factor.factored_live for factor in station.ratings) / max(
            1.0, station.distribution_factor
        )
        pitch_in = studs.usable_pitch_in(composite, shear_range_kip, per_row, spec, cycles)
        if pitch_in < governing_pitch_in:
            governing_pitch_in = pitch_in
            at_station_ft = station.station_ft
    click.echo(f"fatigue  {governing_pitch_in:.2f} in pitch, governed at {at_station_ft:g} ft")
    if governing_pitch_in <= low_in:
        click.echo("fatigue  at the minimum spacing, which wants more studs per row")

    total_shear_kip = sum(
        max(factor.factored_live for factor in station.ratings) for station in results
    )
    rows = studs.rows_needed_for_strength(total_shear_kip, spec, girder.deck.fc_ksi, per_row)
    click.echo(f"strength {rows} row(s) between maximum moment and zero moment")
    click.echo(
        f"strength one stud takes {spec.strength_kip(girder.deck.fc_ksi):.1f} kip, "
        f"{'concrete' if not spec.governed_by_steel(girder.deck.fc_ksi) else 'steel'} governs"
    )
