"""Commands for what was measured, and the fatigue evaluation that reads it.

The spectrum import takes a two column CSV of range and count, which is what
every logger on this inventory writes and what a spreadsheet can produce when
the logger is somebody else's. Anything richer, and there is nothing richer that
matters, would need the raw samples, and by the time a file reaches this command
the samples are already gone.

``fatigue evaluate`` prints what it skipped as loudly as what it evaluated. A
run that quietly says every detail is fine because only two of eleven had a
gauge on them is the failure this command exists to prevent.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import click

from shearstud.analysis import fatiguerun as fr
from shearstud.cli.main import Context, main, pass_context
from shearstud.errors import InputError
from shearstud.fatigue.life import TrafficModel, cycles_per_truck
from shearstud.signals import spectrum as spec
from shearstud.signals.rainflow import Cycle
from shearstud.store import assessment as asm
from shearstud.store import inventory
from shearstud.store import measurement as meas
from shearstud.store.measurement import CampaignRecord, SpectrumQuality
from shearstud.structure.gauge import GaugeInstall


@main.group()
def gauge() -> None:
    """Gauges on the structures."""


@gauge.command("list")
@click.option("--detail", default=None, help="Only the gauges on one detail.")
@pass_context
def list_gauges(ctx: Context, detail: str | None) -> None:
    """Every gauge in the book."""
    path = ctx.require_book()
    installs = meas.load_gauges(path, detail)
    if not installs:
        click.echo("no gauges")
        return
    for install in installs:
        removed = install.removed_on.isoformat() if install.removed_on else "in service"
        click.echo(
            f"{install.gauge_id:<12}{install.detail_id:<12}{install.orientation:<14}"
            f"{install.installed_on}  {removed}"
        )


@gauge.command("add")
@click.argument("gauge_id")
@click.argument("detail_id")
@click.option("--installed", required=True, help="Date the gauge was bonded, YYYY-MM-DD.")
@click.option(
    "--orientation",
    type=click.Choice(["longitudinal", "transverse", "diagonal"]),
    default="longitudinal",
    show_default=True,
    help="Which way the grid runs relative to the girder axis.",
)
@click.option("--factor", type=float, default=2.10, show_default=True, help="Gauge factor.")
@click.option(
    "--limit", "limit_ue", type=float, default=1500.0, show_default=True, help="Channel limit, ue."
)
@click.option("--removed", default=None, help="Date the gauge came off, YYYY-MM-DD.")
@pass_context
def add_gauge(
    ctx: Context,
    gauge_id: str,
    detail_id: str,
    installed: str,
    orientation: str,
    factor: float,
    limit_ue: float,
    removed: str | None,
) -> None:
    """Record a gauge installation."""
    path = ctx.require_book()
    meas.save_gauge(
        path,
        GaugeInstall(
            gauge_id=gauge_id,
            detail_id=detail_id,
            orientation=orientation,
            gauge_factor=factor,
            installed_on=date.fromisoformat(installed),
            channel_limit_ue=limit_ue,
            removed_on=None if removed is None else date.fromisoformat(removed),
        ),
    )
    click.echo(f"recorded {gauge_id} on {detail_id}")


@main.group()
def campaign() -> None:
    """Measurement campaigns."""


@campaign.command("list")
@click.argument("number")
@pass_context
def list_campaigns(ctx: Context, number: str) -> None:
    """Campaigns on one structure, oldest first."""
    path = ctx.require_book()
    records = meas.load_campaigns(path, number)
    if not records:
        click.echo(f"no campaigns on {number}")
        return
    for record in records:
        gauges = meas.gauges_in_campaign(path, record.campaign_id)
        click.echo(
            f"{record.campaign_id:<14}{record.started_on} to {record.ended_on}  "
            f"{record.days:>5.0f} d  {len(gauges):>2} gauges  {record.note}"
        )


@campaign.command("add")
@click.argument("campaign_id")
@click.argument("number")
@click.option("--from", "started", required=True, help="First day, YYYY-MM-DD.")
@click.option("--to", "ended", required=True, help="Last day, YYYY-MM-DD.")
@click.option(
    "--seasonal",
    "seasonal_factor",
    type=float,
    default=1.0,
    show_default=True,
    help="Seasonal factor.",
)
@click.option("--note", default="", help="What the campaign was for.")
@pass_context
def add_campaign(
    ctx: Context,
    campaign_id: str,
    number: str,
    started: str,
    ended: str,
    seasonal_factor: float,
    note: str,
) -> None:
    """Record a measurement campaign."""
    path = ctx.require_book()
    if not inventory.exists(path, number):
        raise click.ClickException(f"no structure {number} in the book")
    meas.save_campaign(
        path,
        CampaignRecord(
            campaign_id=campaign_id,
            structure_number=number,
            started_on=date.fromisoformat(started),
            ended_on=date.fromisoformat(ended),
            seasonal_factor=seasonal_factor,
            note=note,
        ),
    )
    click.echo(f"recorded {campaign_id} on {number}")


@main.command("spectrum")
@click.argument("campaign_id")
@click.argument("gauge_id")
@click.argument("counts", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--bin-width", "bin_width_ue", type=float, default=5.0, show_default=True, help="Bin width, ue."
)
@click.option(
    "--dropout",
    "dropout_frac",
    type=float,
    default=0.0,
    show_default=True,
    help="Dropout fraction.",
)
@click.option(
    "--railed", "railed_frac", type=float, default=0.0, show_default=True, help="Railed fraction."
)
@pass_context
def import_spectrum(
    ctx: Context,
    campaign_id: str,
    gauge_id: str,
    counts: Path,
    bin_width_ue: float,
    dropout_frac: float,
    railed_frac: float,
) -> None:
    """Read a two column range and count file into the book."""
    path = ctx.require_book()
    cycles = _read_counts(counts)
    built = spec.build(gauge_id, cycles, bin_width_ue)
    meas.save_spectrum(
        path,
        campaign_id,
        built,
        SpectrumQuality(dropout_frac=dropout_frac, railed_frac=railed_frac),
    )
    click.echo(f"stored {built.total_count:.0f} cycles in {len(built)} bins for {gauge_id}")


def _read_counts(path: Path) -> list[Cycle]:
    """Read range and count pairs, skipping a header row if there is one."""
    out: list[Cycle] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for line_number, row in enumerate(csv.reader(handle), start=1):
            if not row or not row[0].strip():
                continue
            if len(row) < 2:
                raise InputError(f"{path.name} line {line_number}: needs a range and a count")
            try:
                range_ue = float(row[0])
                count = float(row[1])
            except ValueError:
                if line_number == 1:
                    continue
                raise InputError(
                    f"{path.name} line {line_number}: {row[0]!r} and {row[1]!r} are not numbers"
                ) from None
            out.append(Cycle(range_ue=range_ue, mean_ue=0.0, count=count))
    if not out:
        raise InputError(f"{path.name} holds no cycle counts")
    return out


@main.group()
def fatigue() -> None:
    """Fatigue evaluation."""


@fatigue.command("evaluate")
@click.argument("number")
@click.argument("campaign_id")
@click.option("--growth", type=float, default=None, help="Override the recorded traffic growth.")
@click.option("--allow-poor-records", is_flag=True, help="Evaluate untrustworthy records too.")
@click.option("--save", is_flag=True, help="Write the evaluations into the book.")
@pass_context
def evaluate_command(
    ctx: Context,
    number: str,
    campaign_id: str,
    growth: float | None,
    allow_poor_records: bool,
    save: bool,
) -> None:
    """Evaluate every detail on a structure against one campaign."""
    path = ctx.require_book()
    record = inventory.load(path, number)
    traffic = _traffic_for(path, number, record.length_ft, growth)
    result = fr.run(
        path,
        record,
        campaign_id,
        traffic,
        require_trustworthy=not allow_poor_records,
    )
    for evaluation in sorted(result.evaluated, key=lambda e: e.years_remaining):
        life = "indefinite" if evaluation.infinite_life else f"{evaluation.years_remaining:.0f} yr"
        click.echo(
            f"{evaluation.detail_id:<12}{evaluation.detail_category:<4}"
            f"{evaluation.effective_range_ksi:>6.2f} ksi  {life:>12}  {evaluation.verdict}"
        )
    for reason in fr.SKIP_REASONS:
        skipped = result.skipped_for(reason)
        if skipped:
            click.echo(f"skipped ({reason}): {', '.join(skipped)}")
    click.echo(
        f"{len(result.evaluated)} of {result.detail_count} details measured, "
        f"re evaluate in {fr.interval_years(result):.0f} years"
    )
    if not save:
        return
    today = date.today()
    for evaluation in result.evaluated:
        asm.save_evaluation(path, evaluation, campaign_id, today)
    click.echo(f"saved {len(result.evaluated)} evaluations")


def _traffic_for(path: Path, number: str, length_ft: float, growth: float | None) -> TrafficModel:
    policy = inventory.load_policy(path, number)
    continuous = inventory.is_continuous(path, number)
    return TrafficModel(
        adtt=policy.adtt,
        lanes_available=policy.lanes_available,
        growth_pct_per_yr=policy.growth_pct_per_yr if growth is None else growth,
        cycles_per_passage=cycles_per_truck(length_ft, continuous=continuous),
    )
