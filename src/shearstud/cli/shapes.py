"""Commands for the rolled shape catalogue.

The catalogue is what the older stringers in this inventory are made of, and
the reason it needs a command of its own is the idealisation error. This
package builds a section out of three rectangles, and a rolled beam is not
three rectangles: it has fillets between the web and the flanges that carry
steel the idealisation throws away. The published inertia is therefore always
a little larger than the one this package computes from the same dimensions.

That gap is small, it is systematic, and it is worth being able to look at,
because on a deep narrow flanged shape it reaches three per cent and somebody
comparing a hand calculation against this tool will find it and want to know
whether it is a bug.
"""

from __future__ import annotations

import click

from shearstud.cli.main import main
from shearstud.geometry import rolled


@main.group()
def shape() -> None:
    """The rolled shape catalogue the older stringers come out of."""


@shape.command("list")
@click.option("--starts-with", default=None, help="Only designations beginning with this.")
@click.option("--sort-depth", is_flag=True, help="Deepest first instead of by designation.")
def list_shapes(starts_with: str | None, sort_depth: bool) -> None:
    """Every shape in the catalogue."""
    wanted = rolled.designations()
    if starts_with is not None:
        prefix = starts_with.strip().upper()
        wanted = [name for name in wanted if name.startswith(prefix)]
    shapes = [rolled.shape(name) for name in wanted]
    if sort_depth:
        shapes.sort(key=lambda found: -found.depth_in)
    for found in shapes:
        click.echo(
            f"{found.designation:<12}{found.depth_in:>6.2f} deep  "
            f"{found.flange_width_in:>6.2f} flange  "
            f"{found.area_in2:>6.2f} in2  {found.inertia_in4:>8.0f} in4"
        )
    click.echo(f"{len(shapes)} shape(s)")


@shape.command("show")
@click.argument("designation")
def show_shape(designation: str) -> None:
    """One shape's published dimensions, and what the idealisation makes of it."""
    found = rolled.shape(designation)
    section = found.section()
    click.echo(f"shape      {found.designation}")
    click.echo(f"depth      {found.depth_in:g} in, web {found.web_depth_in:g} in clear")
    click.echo(
        f"flange     {found.flange_width_in:g} by {found.flange_thickness_in:g} in, "
        f"web {found.web_thickness_in:g} in"
    )
    click.echo(f"published  A {found.area_in2:g} in2  I {found.inertia_in4:g} in4")
    click.echo(f"idealised  A {section.area_in2:.2f} in2  I {section.inertia_in4:.0f} in4")
    click.echo(
        f"difference {found.idealisation_error_frac():.2%} of the published inertia, "
        f"which is the fillets"
    )


@shape.command("compare")
@click.option("--worst", type=int, default=5, show_default=True, help="How many to print.")
def compare_shapes(worst: int) -> None:
    """The shapes the three rectangle idealisation fits least well.

    Deep shapes with narrow flanges are at the top of this list, because the
    fillet is a larger share of a section that has less flange in it.
    """
    if worst < 1:
        raise click.BadParameter("a list of nothing is not a list")
    shapes = [rolled.shape(name) for name in rolled.designations()]
    shapes.sort(key=lambda found: -found.idealisation_error_frac())
    for found in shapes[:worst]:
        click.echo(
            f"{found.designation:<12}{found.idealisation_error_frac():>7.2%}  "
            f"published {found.inertia_in4:>8.0f}  "
            f"idealised {found.section().inertia_in4:>8.0f}"
        )
    largest = shapes[0].idealisation_error_frac()
    click.echo(f"worst fit {largest:.2%}, on {shapes[0].designation}")
