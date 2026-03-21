"""One run through the whole package, from an empty directory to a posting.

The unit tests say each piece is right. This says the pieces fit, which is a
different claim and the one that breaks first: a repository that stores a
spectrum the evaluation cannot read, or a rating run that produces a factor the
posting refuses, passes every unit test and fails here.

It writes into a temporary directory and leaves nothing behind. Every step
asserts something about its own result rather than merely completing, because a
smoke test that only checks for the absence of an exception passes on a rating
of zero.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Final

from shearstud.analysis import fatiguerun as fr
from shearstud.analysis import programrun as pr
from shearstud.analysis import ratingrun as rr
from shearstud.analysis.ratingrun import RatingSettings
from shearstud.errors import ShearstudError
from shearstud.fatigue.life import TrafficModel, cycles_per_truck
from shearstud.loads import vehicles
from shearstud.program import interval, priority
from shearstud.rating import factors as fac
from shearstud.rating import posting as post
from shearstud.signals import rainflow, spectrum
from shearstud.store import assessment as asm
from shearstud.store import importer, inventory, measurement, migrate, programme
from shearstud.store.inventory import StructurePolicy
from shearstud.store.measurement import CampaignRecord
from shearstud.store.programme import ProgrammeRow
from shearstud.structure.gauge import ORIENTATION_LONGITUDINAL, GaugeInstall
from shearstud.tools.walk import REPO_ROOT

#: The structure the smoke run works on.
EXAMPLE: Final[Path] = REPO_ROOT / "examples" / "salt-fork-creek.json"

#: The campaign the smoke run records.
CAMPAIGN_ID: Final[str] = "C-2026-04"

#: A fortnight of one gauge on a busy rural route, as a strain history the
#: rainflow counter turns into a spectrum.
SAMPLE_PEAK_UE: Final[float] = 210.0
SAMPLE_EVENTS: Final[int] = 400

#: What the last inspection of this structure found. Fair rather than good, so
#: that the run exercises the branch where the extension is blocked and not the
#: one where everything is clean.
CONDITION_RATING: Final[int] = 6

#: The route it carries and what closing it would cost.
DAILY_TRAFFIC: Final[int] = 2600
DETOUR_MI: Final[float] = 11.0


def _strain_history() -> list[float]:
    """A synthetic fortnight: a big loop per truck with two small ones inside."""
    out: list[float] = [0.0]
    for index in range(SAMPLE_EVENTS):
        peak = SAMPLE_PEAK_UE * (0.55 + 0.45 * ((index % 7) / 6.0))
        out.extend([peak, 0.35 * peak, 0.60 * peak, 0.20 * peak, 0.0])
    return out


def run(book: Path) -> list[str]:
    """Do the whole thing, returning a line per step for the report."""
    lines: list[str] = []

    applied = migrate.upgrade(book)
    # Against the code's own list rather than a number written here. A count
    # written here has to be edited by whoever adds a migration, and the edit
    # that keeps the smoke run green is the one that stops it checking.
    expected = list(range(1, migrate.newest_version() + 1))
    assert applied == expected, f"expected migrations {expected}, got {applied}"
    lines.append(f"schema      migrations {', '.join(str(v) for v in applied)} applied")

    structure = importer.read(EXAMPLE)
    policy = StructurePolicy(
        steel_grade="A36",
        member_condition="fair",
        redundancy="redundant",
        adtt=1400.0,
        lanes_available=2,
        growth_pct_per_yr=1.8,
    )
    inventory.save(book, structure, policy)
    reloaded = inventory.load(book, str(structure.number))
    assert reloaded.girder_count == structure.girder_count
    assert len(reloaded.details()) == len(structure.details())
    lines.append(
        f"inventory   {reloaded.number} loaded: {reloaded.girder_count} girders, "
        f"{len(reloaded.details())} details"
    )

    settings = RatingSettings(
        steel_grade=policy.steel_grade,
        member_condition=policy.member_condition,
        redundancy=policy.redundancy,
        adtt=policy.adtt,
        overlay_in=2.0,
        stations_per_span=10,
    )
    results = rr.rate_structure(reloaded, vehicles.legal_fleet(), settings)
    governing = rr.governing(results)
    assert results, "the rating run produced nothing"
    assert governing.value > 0.0, "the governing rating factor is not positive"
    lines.append(
        f"rating      {len(results)} stations, governing RF {governing.value:.2f} "
        f"on {governing.vehicle}"
    )

    by_silhouette = {}
    for silhouette, name in post.SIGN_VEHICLES.items():
        run_results = rr.rate_structure(reloaded, [vehicles.vehicle(name)], settings)
        by_silhouette[silhouette] = rr.governing(run_results)
    decision = post.decide(by_silhouette)
    asm.save_posting(book, str(structure.number), decision, date(2026, 4, 20))
    assert asm.current_outcome(book, str(structure.number)) == decision.outcome
    lines.append(f"posting     {decision.outcome} at RF {decision.governing_factor:.2f}")

    detail_id = reloaded.girder("G2").details[0].detail_id
    measurement.save_gauge(
        book,
        GaugeInstall(
            gauge_id="G2-BF-01",
            detail_id=detail_id,
            orientation=ORIENTATION_LONGITUDINAL,
            gauge_factor=2.10,
            installed_on=date(2026, 3, 30),
            channel_limit_ue=1500.0,
        ),
    )
    measurement.save_campaign(
        book,
        CampaignRecord(
            campaign_id=CAMPAIGN_ID,
            structure_number=str(structure.number),
            started_on=date(2026, 4, 1),
            ended_on=date(2026, 4, 14),
            seasonal_factor=1.1,
            note="spring haul, one gauge on the G2 cover plate end",
        ),
    )
    cycles = rainflow.count_cycles(_strain_history())
    counted = spectrum.build("G2-BF-01", cycles, 5.0)
    assert counted.total_count > SAMPLE_EVENTS, "the counter found fewer loops than trucks"
    measurement.save_spectrum(book, CAMPAIGN_ID, counted)
    lines.append(
        f"measurement {counted.total_count:.0f} cycles in {len(counted)} bins, "
        f"largest {counted.largest_range_ue:.0f} ue"
    )

    traffic = TrafficModel(
        adtt=policy.adtt,
        lanes_available=policy.lanes_available,
        growth_pct_per_yr=policy.growth_pct_per_yr,
        cycles_per_passage=cycles_per_truck(reloaded.length_ft, continuous=False),
    )
    evaluated = fr.run(book, reloaded, CAMPAIGN_ID, traffic)
    assert evaluated.evaluated, "the fatigue run evaluated nothing"
    assert evaluated.unmeasured_count > 0, "every detail was measured, which is not this case"
    worst = evaluated.worst()
    for evaluation in evaluated.evaluated:
        asm.save_evaluation(book, evaluation, CAMPAIGN_ID, date(2026, 4, 20))
    lines.append(
        f"fatigue     {len(evaluated.evaluated)} of {evaluated.detail_count} measured, "
        f"worst {worst.detail_id} at {worst.verdict}"
    )

    assert asm.load_ratings(book, str(structure.number)) == [], "nothing should be rated yet"
    history = asm.load_evaluations(book, worst.detail_id)
    assert history, "the evaluation did not reach the book of record"
    lines.append(f"record      {len(history)} evaluation(s) stored, book clean")

    # Nothing has been inspected under the programme yet, so the structure is a
    # gap rather than a low ranking. That distinction is the whole point of the
    # module and it is worth holding here rather than only in its unit tests.
    number = str(structure.number)
    before = pr.build(book)
    assert before.ranked == (), "a structure with no inspection row should not be ranked"
    assert before.gaps_for(pr.GAP_NO_PROGRAMME) == [number]

    programme.save(
        book,
        ProgrammeRow(
            structure_number=str(structure.number),
            lowest_condition_rating=CONDITION_RATING,
            daily_traffic=DAILY_TRAFFIC,
            detour_mi=DETOUR_MI,
            is_posted=decision.outcome == post.POSTED,
            last_inspected=date(2026, 3, 12),
            updated_on=date(2026, 4, 20),
        ),
    )
    # The rating run reports factors and does not store them, so an inspected
    # structure is still short of a rating until the run is written down. The
    # ranking reads the book and not the run, and this is where that shows.
    inspected = pr.build(book)
    assert inspected.gaps_for(pr.GAP_NEVER_RATED) == [number], (
        "a structure with no stored rating should be a gap, not a ranking"
    )

    written = rr.store(book, number, results, fac.OPERATING, date(2026, 4, 20))
    assert written > 0, "the rating run stored nothing"
    worklist = pr.build(book)
    assert worklist.gaps == (), f"the worklist could not rank anything: {worklist.gaps}"
    assert len(worklist.ranked) == 1
    candidate = worklist.ranked[0]
    band = priority.band_of(candidate)
    decided = interval.decide(candidate.state)
    assert decided.months in interval.ALLOWED_MONTHS
    lines.append(
        f"programme   {candidate.number} in the {band} band, inspect in {decided.months} months"
    )
    return lines


def main(argv: list[str] | None = None) -> int:
    """Run the smoke test and print what each step produced."""
    args = sys.argv[1:] if argv is None else argv
    quiet = "--quiet" in args
    with tempfile.TemporaryDirectory() as directory:
        book = Path(directory) / "smoke.sqlite3"
        try:
            lines = run(book)
        except (ShearstudError, AssertionError) as exc:
            print(f"smoke: FAILED: {exc}")
            return 1
    if not quiet:
        for line in lines:
            print(f"smoke: {line}")
    print("smoke: clean")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
