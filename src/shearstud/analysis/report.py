"""The two reports the office actually sends out.

A structure report goes in a file and is read by one engineer about one bridge.
An inventory report goes to a district and is read by somebody deciding where
the money goes. They are different documents and the difference is not length.

Both of them say what is missing in the same breath as what is known, and both
of them say it first. A report that opens with the numbers it has reads as a
complete picture, and the reader takes the absence of a line about fatigue as
"no fatigue problem" rather than "nobody has ever put a gauge on it". Every
line here that could be a silence is written out as a sentence instead.

Nothing is computed here. Everything is read out of the book, and where the
book has nothing the report says so. That is deliberate: a report that ran the
rating itself would produce numbers nobody could find again, because the
settings it used would be gone the moment it printed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from shearstud.analysis import programrun as pr
from shearstud.errors import StorageError
from shearstud.program import interval, priority
from shearstud.store import assessment as asm
from shearstud.store import inventory
from shearstud.store import programme as prog

#: What a line says when the book has nothing to say.
NOTHING_ON_RECORD: Final[str] = "nothing on record"

#: Width of the label column, so the two reports line up with each other.
LABEL_WIDTH: Final[int] = 12


@dataclass(frozen=True, slots=True)
class Line:
    """One labelled line of a report."""

    label: str
    text: str

    def __str__(self) -> str:
        return f"{self.label:<{LABEL_WIDTH}}{self.text}"

    @property
    def is_a_silence(self) -> bool:
        """True when this line is reporting an absence rather than a number."""
        return self.text.startswith(NOTHING_ON_RECORD)


def _rating_line(path: Path | str, number: str) -> Line:
    try:
        governing = asm.governing_rating(path, number)
    except StorageError:
        return Line("rating", f"{NOTHING_ON_RECORD}, nobody has rated this structure")
    verdict = "carries the legal loads" if governing.is_adequate else "DOES NOT CARRY"
    return Line(
        "rating",
        f"{governing.rating_factor:.2f} on {governing.vehicle} in {governing.effect} "
        f"at {governing.girder_id} {governing.station_ft:g} ft, {verdict} "
        f"(rated {governing.rated_on})",
    )


def _posting_line(path: Path | str, number: str) -> Line:
    outcome = asm.current_outcome(path, number)
    if outcome is None:
        return Line("posting", f"{NOTHING_ON_RECORD}, no posting decision has been made")
    return Line("posting", outcome)


def _fatigue_line(path: Path | str, number: str) -> Line:
    life_years, measured = pr.credited_life_years(path, number)
    if not measured:
        return Line(
            "fatigue",
            f"{NOTHING_ON_RECORD}, no detail on this structure has been measured",
        )
    return Line("fatigue", f"{life_years:.1f} years left at the worst measured detail")


def _programme_lines(path: Path | str, number: str) -> list[Line]:
    row = prog.find(path, number)
    if row is None:
        return [
            Line(
                "inspection",
                f"{NOTHING_ON_RECORD}, never inspected under this programme",
            )
        ]
    life_years, _ = pr.credited_life_years(path, number)
    decision = interval.decide(row.state(life_years))
    return [
        Line("inspection", f"{row.last_inspected}, lowest rating {row.lowest_condition_rating}"),
        Line("interval", f"{decision.months} months, {decision.reason}"),
        Line("next due", str(decision.next_due(row.last_inspected))),
    ]


def structure_report(path: Path | str, number: str) -> list[Line]:
    """Everything the book holds about one structure, absences included."""
    record = inventory.summary(path, number)
    spans = ", ".join(f"{length:g}" for length in record.spans.lengths_ft)
    joined = "continuous" if record.spans.continuous else "simple"
    gauges = f"{record.gauge_count} gauge(s)" if record.is_instrumented else "no gauges"
    out = [
        Line("number", record.number),
        Line("name", record.name),
        Line("built", str(record.year_built) if record.year_built else NOTHING_ON_RECORD),
        Line("spans", f"{spans} ft, {joined}"),
        Line("girders", f"{record.girder_count}, {record.length_ft:g} ft"),
        Line("details", f"{record.detail_count} fatigue details, {gauges}"),
        _rating_line(path, number),
        _posting_line(path, number),
        _fatigue_line(path, number),
    ]
    out.extend(_programme_lines(path, number))
    return out


def silences(lines: list[Line]) -> list[Line]:
    """The lines of a report that are reporting an absence."""
    return [line for line in lines if line.is_a_silence]


def inventory_report(path: Path | str, today: date) -> list[Line]:
    """The district's picture: how much is known, and what is due."""
    worklist = pr.build(path)
    out = [
        Line("structures", str(worklist.structure_count)),
        Line(
            "ranked",
            f"{len(worklist.ranked)} of {worklist.structure_count} ({worklist.ranked_frac:.0%})",
        ),
    ]
    for reason in pr.GAP_REASONS:
        missing = worklist.gaps_for(reason)
        if missing:
            out.append(Line("not ranked", f"{len(missing)} {reason}: {', '.join(missing)}"))
    if worklist.unmeasured:
        out.append(
            Line("unmeasured", f"{len(worklist.unmeasured)} ranked on a credited fatigue life")
        )
    counts = worklist.counts()
    for band in priority.BANDS:
        out.append(Line(band, f"{counts[band]}, ordered by {priority.BAND_MEASURE[band]}"))
    overdue = due_before(path, today)
    out.append(Line("overdue", str(len(overdue)) if overdue else "none"))
    return out


def due_before(path: Path | str, today: date) -> list[tuple[date, str, int]]:
    """Structures past their inspection date, soonest due first."""
    out: list[tuple[date, str, int]] = []
    for row in prog.load_all(path):
        life_years, _ = pr.credited_life_years(path, row.structure_number)
        decision = interval.decide(row.state(life_years))
        if decision.is_overdue(row.last_inspected, today):
            out.append(
                (decision.next_due(row.last_inspected), row.structure_number, decision.months)
            )
    return sorted(out)


def as_text(lines: list[Line]) -> str:
    """A report as one block of text."""
    return "\n".join(str(line) for line in lines)
