"""Evaluating every instrumented detail on a structure from stored spectra.

The rating run reads geometry and produces numbers. This one reads measurements,
and that changes what can go wrong: a detail with no gauge on it cannot be
evaluated, a gauge with a bad record should not be, and a gauge that reads
transverse strain must not be. All three are silences rather than errors if they
are not looked for, so this module reports what it skipped and why alongside
what it evaluated.

A structure whose every instrumented detail is infinite life still has details
nobody measured, and the summary says so. That is the number a bridge engineer
actually wants: not "the measured details are fine" but "eleven of the nineteen
details on this structure have never been measured".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from shearstud.errors import InputError
from shearstud.fatigue import categories as cat
from shearstud.fatigue import evaluation as ev
from shearstud.fatigue import life as lf
from shearstud.program import interval
from shearstud.store import measurement as meas
from shearstud.structure.detail import FatigueDetail
from shearstud.structure.gauge import GaugeInstall
from shearstud.structure.record import Structure

#: Why a detail was not evaluated.
SKIP_NO_GAUGE = "no gauge on this detail"
SKIP_NO_SPECTRUM = "the gauge did not report in this campaign"
SKIP_TRANSVERSE = "the gauge does not read bending stress"
SKIP_UNTRUSTWORTHY = "too much of the record was unusable"
SKIP_REASONS = (SKIP_NO_GAUGE, SKIP_NO_SPECTRUM, SKIP_TRANSVERSE, SKIP_UNTRUSTWORTHY)

#: The most fatigue life the interval rule is allowed to be told about. An
#: infinite life is a statement about one calculation and not about the
#: structure, and it must not walk into a programme decision as a number no
#: threshold can ever fail.
MAX_CREDITED_LIFE_YEARS = 100.0


@dataclass(frozen=True, slots=True)
class SkippedDetail:
    """A detail that was not evaluated, and why."""

    detail_id: str
    reason: str

    def __post_init__(self) -> None:
        if self.reason not in SKIP_REASONS:
            raise InputError(f"unknown skip reason {self.reason!r}")


@dataclass(frozen=True, slots=True)
class RunResult:
    """What a fatigue run produced and what it left out."""

    campaign_id: str
    evaluated: tuple[ev.Evaluation, ...]
    skipped: tuple[SkippedDetail, ...]

    @property
    def detail_count(self) -> int:
        """Every detail the run looked at, evaluated or not."""
        return len(self.evaluated) + len(self.skipped)

    @property
    def measured_frac(self) -> float:
        """Share of the structure's details that carried a usable measurement."""
        if self.detail_count == 0:
            return 0.0
        return len(self.evaluated) / self.detail_count

    @property
    def unmeasured_count(self) -> int:
        """How many details nobody has a reading for."""
        return sum(1 for s in self.skipped if s.reason == SKIP_NO_GAUGE)

    def worst(self) -> ev.Evaluation:
        """The evaluated detail with the least life left."""
        return ev.worst_of(list(self.evaluated))

    def needing_attention(self) -> list[ev.Evaluation]:
        """Evaluated details that are not comfortable, worst first."""
        return ev.needing_attention(list(self.evaluated))

    def skipped_for(self, reason: str) -> list[str]:
        """Detail ids skipped for one reason, sorted."""
        if reason not in SKIP_REASONS:
            raise InputError(f"unknown skip reason {reason!r}")
        return sorted(s.detail_id for s in self.skipped if s.reason == reason)


def _gauge_for(
    detail: FatigueDetail, gauges: Sequence[GaugeInstall]
) -> GaugeInstall | SkippedDetail:
    watching = [g for g in gauges if g.detail_id == detail.detail_id]
    if not watching:
        return SkippedDetail(detail.detail_id, SKIP_NO_GAUGE)
    axial = [g for g in watching if g.reads_axial_stress]
    if not axial:
        return SkippedDetail(detail.detail_id, SKIP_TRANSVERSE)
    return sorted(axial, key=lambda g: g.gauge_id)[0]


def run(
    path: Path | str,
    structure: Structure,
    campaign_id: str,
    traffic: lf.TrafficModel,
    *,
    require_trustworthy: bool = True,
) -> RunResult:
    """Evaluate every detail on a structure against one campaign."""
    campaigns = {c.campaign_id: c for c in meas.load_campaigns(path, str(structure.number))}
    if campaign_id not in campaigns:
        raise InputError(f"no campaign {campaign_id!r} on {structure.number}")
    record = campaigns[campaign_id]
    campaign = ev.Campaign(days=record.days, seasonal_factor=record.seasonal_factor)
    gauges = meas.load_gauges(path)
    reporting = set(meas.gauges_in_campaign(path, campaign_id))

    evaluated: list[ev.Evaluation] = []
    skipped: list[SkippedDetail] = []
    for detail in structure.details():
        found = _gauge_for(detail, gauges)
        if isinstance(found, SkippedDetail):
            skipped.append(found)
            continue
        if found.gauge_id not in reporting:
            skipped.append(SkippedDetail(detail.detail_id, SKIP_NO_SPECTRUM))
            continue
        quality = meas.load_quality(path, campaign_id, found.gauge_id)
        if require_trustworthy and not quality.is_trustworthy:
            skipped.append(SkippedDetail(detail.detail_id, SKIP_UNTRUSTWORTHY))
            continue
        spectrum = meas.load_spectrum(path, campaign_id, found.gauge_id)
        evaluated.append(
            ev.evaluate(
                detail_id=detail.detail_id,
                measured=spectrum,
                campaign=campaign,
                detail=cat.category(detail.category_name),
                traffic=traffic,
            )
        )
    return RunResult(campaign_id=campaign_id, evaluated=tuple(evaluated), skipped=tuple(skipped))


def inspection_state(
    result: RunResult,
    lowest_condition_rating: int,
    *,
    is_posted: bool = False,
    has_nonredundant_members: bool = False,
) -> interval.StructureState:
    """What the interval rule needs to know, with the fatigue life filled in.

    A run that evaluated nothing does not get the benefit of the doubt. The
    fatigue life goes in as zero, which fires the shortener, because a structure
    nobody has a reading for is not a structure known to be fine.
    """
    if not result.evaluated:
        life_years = 0.0
    else:
        measured = ev.structure_life_years(list(result.evaluated))
        life_years = min(measured, MAX_CREDITED_LIFE_YEARS)
    return interval.StructureState(
        lowest_condition_rating=lowest_condition_rating,
        is_posted=is_posted,
        has_nonredundant_members=has_nonredundant_members,
        fatigue_life_years=life_years,
    )


def inspection_due(
    result: RunResult,
    last_inspected: date,
    today: date,
    lowest_condition_rating: int,
    *,
    is_posted: bool = False,
    has_nonredundant_members: bool = False,
) -> bool:
    """Whether the structure is past its inspection date."""
    state = inspection_state(
        result,
        lowest_condition_rating,
        is_posted=is_posted,
        has_nonredundant_members=has_nonredundant_members,
    )
    return interval.decide(state).is_overdue(last_inspected, today)
