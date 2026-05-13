"""The measurement and fatigue commands, and what they say they skipped."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from shearstud.cli import main
from shearstud.store import assessment as asm
from shearstud.store import db
from shearstud.store import measurement as meas
from tests.support import cover_plate_end, document, stiffener_weld

pytestmark = pytest.mark.cli

NUMBER = "18-SH-0473"
CAMPAIGN = "C-2025-04"
UE_PER_KSI = 1.0e6 / 29000.0


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def instrumented() -> dict[str, Any]:
    """One girder carrying the two details the measurement tests use."""
    return document(
        girder_count=1,
        details_on_first=[cover_plate_end(), stiffener_weld()],
    )


@pytest.fixture
def wired(runner: CliRunner, book: Path, tmp_path: Path) -> Path:
    doc = tmp_path / "structure.json"
    doc.write_text(json.dumps(instrumented()), encoding="utf-8")
    assert (
        runner.invoke(
            main,
            ["--book", str(book), "structure", "import", str(doc), "--adtt", "1200"],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            main,
            [
                "--book",
                str(book),
                "campaign",
                "add",
                CAMPAIGN,
                NUMBER,
                "--from",
                "2025-04-01",
                "--to",
                "2025-04-14",
            ],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            main,
            ["--book", str(book), "gauge", "add", "g1", "D1", "--installed", "2025-03-14"],
        ).exit_code
        == 0
    )
    return book


def counts_file(tmp_path: Path, range_ksi: float = 6.0, count: float = 60000.0) -> Path:
    path = tmp_path / "counts.csv"
    path.write_text(f"range_ue,count\n{range_ksi * UE_PER_KSI:.4f},{count}\n", encoding="utf-8")
    return path


def test_an_empty_book_lists_no_gauges(runner: CliRunner, book: Path) -> None:
    result = runner.invoke(main, ["--book", str(book), "gauge", "list"])
    assert "no gauges" in result.output


def test_a_gauge_can_be_added_and_listed(runner: CliRunner, wired: Path) -> None:
    result = runner.invoke(main, ["--book", str(wired), "gauge", "list"])
    assert result.exit_code == 0
    assert "g1" in result.output
    assert "in service" in result.output


def test_a_removed_gauge_shows_its_date(runner: CliRunner, wired: Path) -> None:
    runner.invoke(
        main,
        [
            "--book",
            str(wired),
            "gauge",
            "add",
            "g1",
            "D1",
            "--installed",
            "2025-03-14",
            "--removed",
            "2026-02-01",
        ],
    )
    result = runner.invoke(main, ["--book", str(wired), "gauge", "list"])
    assert "2026-02-01" in result.output


def test_gauges_can_be_narrowed_to_a_detail(runner: CliRunner, wired: Path) -> None:
    result = runner.invoke(main, ["--book", str(wired), "gauge", "list", "--detail", "D2"])
    assert "no gauges" in result.output


def test_a_gauge_on_a_detail_that_is_not_there_is_reported(runner: CliRunner, wired: Path) -> None:
    result = runner.invoke(
        main, ["--book", str(wired), "gauge", "add", "g9", "nowhere", "--installed", "2025-03-14"]
    )
    assert result.exit_code != 0


def test_a_bad_gauge_factor_is_reported(runner: CliRunner, wired: Path) -> None:
    result = runner.invoke(
        main,
        [
            "--book",
            str(wired),
            "gauge",
            "add",
            "g2",
            "D2",
            "--installed",
            "2025-03-14",
            "--factor",
            "4.0",
        ],
    )
    assert result.exit_code != 0


def test_campaigns_can_be_listed(runner: CliRunner, wired: Path) -> None:
    result = runner.invoke(main, ["--book", str(wired), "campaign", "list", NUMBER])
    assert result.exit_code == 0
    assert CAMPAIGN in result.output
    assert "14 d" in result.output


def test_a_structure_with_no_campaigns_says_so(runner: CliRunner, book: Path) -> None:
    result = runner.invoke(main, ["--book", str(book), "campaign", "list", "99-IH-0001"])
    assert "no campaigns" in result.output


def test_a_campaign_on_a_structure_that_is_not_there_is_refused(
    runner: CliRunner, book: Path
) -> None:
    result = runner.invoke(
        main,
        [
            "--book",
            str(book),
            "campaign",
            "add",
            "C-1",
            "99-IH-0001",
            "--from",
            "2025-04-01",
            "--to",
            "2025-04-14",
        ],
    )
    assert result.exit_code != 0
    assert "no structure" in result.output


def test_a_campaign_that_ends_before_it_starts_is_reported(runner: CliRunner, wired: Path) -> None:
    result = runner.invoke(
        main,
        [
            "--book",
            str(wired),
            "campaign",
            "add",
            "C-2",
            NUMBER,
            "--from",
            "2025-04-14",
            "--to",
            "2025-04-01",
        ],
    )
    assert result.exit_code != 0


def test_a_spectrum_can_be_imported(runner: CliRunner, wired: Path, tmp_path: Path) -> None:
    counts = counts_file(tmp_path)
    result = runner.invoke(main, ["--book", str(wired), "spectrum", CAMPAIGN, "g1", str(counts)])
    assert result.exit_code == 0, result.output
    assert "60000 cycles" in result.output
    assert meas.load_spectrum(wired, CAMPAIGN, "g1").total_count == pytest.approx(60000.0)


def test_the_header_row_is_skipped(runner: CliRunner, wired: Path, tmp_path: Path) -> None:
    counts = counts_file(tmp_path)
    runner.invoke(main, ["--book", str(wired), "spectrum", CAMPAIGN, "g1", str(counts)])
    assert len(meas.load_spectrum(wired, CAMPAIGN, "g1")) == 1


def test_the_quality_fractions_are_stored(runner: CliRunner, wired: Path, tmp_path: Path) -> None:
    counts = counts_file(tmp_path)
    runner.invoke(
        main,
        [
            "--book",
            str(wired),
            "spectrum",
            CAMPAIGN,
            "g1",
            str(counts),
            "--dropout",
            "0.2",
            "--railed",
            "0.05",
        ],
    )
    quality = meas.load_quality(wired, CAMPAIGN, "g1")
    assert quality.dropout_frac == pytest.approx(0.2)
    assert quality.railed_frac == pytest.approx(0.05)


def test_an_empty_counts_file_is_reported(runner: CliRunner, wired: Path, tmp_path: Path) -> None:
    counts = tmp_path / "empty.csv"
    counts.write_text("range_ue,count\n", encoding="utf-8")
    result = runner.invoke(main, ["--book", str(wired), "spectrum", CAMPAIGN, "g1", str(counts)])
    assert result.exit_code != 0
    assert "no cycle counts" in result.output


def test_a_one_column_file_is_reported(runner: CliRunner, wired: Path, tmp_path: Path) -> None:
    counts = tmp_path / "thin.csv"
    counts.write_text("40.0\n", encoding="utf-8")
    result = runner.invoke(main, ["--book", str(wired), "spectrum", CAMPAIGN, "g1", str(counts)])
    assert result.exit_code != 0
    assert "needs a range and a count" in result.output


def test_a_non_numeric_row_is_reported(runner: CliRunner, wired: Path, tmp_path: Path) -> None:
    counts = tmp_path / "bad.csv"
    counts.write_text("range_ue,count\n40.0,1000\nfour,many\n", encoding="utf-8")
    result = runner.invoke(main, ["--book", str(wired), "spectrum", CAMPAIGN, "g1", str(counts)])
    assert result.exit_code != 0
    assert "are not numbers" in result.output


def evaluated(
    runner: CliRunner,
    book: Path,
    tmp_path: Path,
    range_ksi: float = 6.0,
    extra: list[str] | None = None,
) -> Any:
    counts = counts_file(tmp_path, range_ksi=range_ksi)
    runner.invoke(main, ["--book", str(book), "spectrum", CAMPAIGN, "g1", str(counts)])
    argv = ["--book", str(book), "fatigue", "evaluate", NUMBER, CAMPAIGN, *(extra or [])]
    return runner.invoke(main, argv)


def test_the_evaluation_prints_a_line_per_measured_detail(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    result = evaluated(runner, wired, tmp_path)
    assert result.exit_code == 0, result.output
    assert "D1" in result.output


def test_the_evaluation_names_what_it_skipped(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    result = evaluated(runner, wired, tmp_path)
    assert "skipped" in result.output
    assert "D2" in result.output


def test_the_evaluation_reports_the_coverage(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    result = evaluated(runner, wired, tmp_path)
    assert "1 of 2 details measured" in result.output


def test_the_evaluation_gives_an_inspection_interval(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    result = evaluated(runner, wired, tmp_path)
    assert "inspect again in" in result.output
    assert "months" in result.output


def test_a_poor_condition_rating_shortens_what_the_command_prints(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    result = evaluated(runner, wired, tmp_path, range_ksi=0.4, extra=["--condition", "3"])
    assert "inspect again in 12 months" in result.output
    assert "shortened by condition" in result.output


def test_a_sound_structure_with_a_quiet_detail_earns_the_long_interval(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    result = evaluated(runner, wired, tmp_path, range_ksi=0.4, extra=["--condition", "8"])
    assert "inspect again in 48 months" in result.output


def test_a_condition_rating_off_the_scale_is_refused(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    result = evaluated(runner, wired, tmp_path, extra=["--condition", "11"])
    assert result.exit_code != 0


def test_a_quiet_detail_reads_indefinite(runner: CliRunner, wired: Path, tmp_path: Path) -> None:
    result = evaluated(runner, wired, tmp_path, range_ksi=0.4)
    assert "indefinite" in result.output


def test_the_evaluation_writes_nothing_by_default(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    evaluated(runner, wired, tmp_path)
    assert asm.load_evaluations(wired, "D1") == []


def test_saving_writes_the_evaluations(runner: CliRunner, wired: Path, tmp_path: Path) -> None:
    counts = counts_file(tmp_path)
    runner.invoke(main, ["--book", str(wired), "spectrum", CAMPAIGN, "g1", str(counts)])
    result = runner.invoke(
        main, ["--book", str(wired), "fatigue", "evaluate", NUMBER, CAMPAIGN, "--save"]
    )
    assert result.exit_code == 0
    assert asm.load_evaluations(wired, "D1")


def test_a_campaign_that_is_not_there_is_reported(runner: CliRunner, wired: Path) -> None:
    result = runner.invoke(main, ["--book", str(wired), "fatigue", "evaluate", NUMBER, "C-1999-01"])
    assert result.exit_code != 0
    assert "no campaign" in result.output


def strain_file(tmp_path: Path, trucks: int = 12, railed: bool = False) -> Path:
    """A synthetic logger file: quiet stretches with triangular passes in them."""
    samples: list[float] = []
    for index in range(trucks):
        samples.extend([0.0] * 12)
        peak = 180.0 * (0.6 + 0.4 * ((index % 5) / 4.0))
        up = [peak * (step + 1) / 11.0 for step in range(10)]
        samples.extend([*up, peak, *reversed(up)])
    samples.extend([0.0] * 12)
    if railed:
        samples[40:70] = [1500.0] * 30
    path = tmp_path / "strain.csv"
    rows = ["timestamp,ue", f"2026-04-01T06:00:00,{samples[0]:.4f}"]
    rows.extend(f",{value:.4f}" for value in samples[1:])
    path.write_text("\n".join(rows), encoding="utf-8")
    return path


def imported_record(
    runner: CliRunner, book: Path, tmp_path: Path, *extra: str, railed: bool = False
) -> Any:
    strain = strain_file(tmp_path, railed=railed)
    argv = [
        "--book",
        str(book),
        "record",
        CAMPAIGN,
        "g1",
        str(strain),
        "--rate-hz",
        "20",
        *extra,
    ]
    return runner.invoke(main, argv)


def test_a_raw_record_reads_and_reports(runner: CliRunner, wired: Path, tmp_path: Path) -> None:
    result = imported_record(runner, wired, tmp_path)
    assert result.exit_code == 0, result.output
    assert "read" in result.output
    assert "samples over" in result.output


def test_the_record_command_reports_the_quality(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    result = imported_record(runner, wired, tmp_path)
    assert "100.0% usable" in result.output


def test_a_railed_record_is_called_out(runner: CliRunner, wired: Path, tmp_path: Path) -> None:
    result = imported_record(runner, wired, tmp_path, railed=True)
    assert "NOT TRUSTWORTHY" in result.output


def test_the_record_command_counts_the_trucks(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    result = imported_record(runner, wired, tmp_path)
    assert "events    12," in result.output


def test_the_record_command_counts_the_cycles(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    result = imported_record(runner, wired, tmp_path)
    assert "cycles" in result.output
    assert "bins" in result.output


def test_the_events_flag_prints_a_line_per_truck(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    quiet = imported_record(runner, wired, tmp_path)
    loud = imported_record(runner, wired, tmp_path, "--events")
    assert len(loud.output.splitlines()) - len(quiet.output.splitlines()) == 12
    assert "peak" in loud.output


def test_the_record_command_writes_nothing_unless_asked(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    imported_record(runner, wired, tmp_path)
    assert db.row_count(wired, "spectra") == 0


def test_the_record_command_saves_when_asked(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    result = imported_record(runner, wired, tmp_path, "--save")
    assert "saved" in result.output
    assert db.row_count(wired, "spectra") > 0


def test_the_saved_spectrum_carries_the_quality(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    imported_record(runner, wired, tmp_path, "--save", railed=True)
    quality = meas.load_quality(wired, CAMPAIGN, "g1")
    assert quality.railed_frac > 0.0


def test_the_channel_limit_comes_off_the_gauge(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    # The gauge was added with the default limit, and the railed samples sit
    # at it. Nothing on the command line said so.
    result = imported_record(runner, wired, tmp_path, railed=True)
    assert "railed" in result.output
    assert "0.0% railed" not in result.output


def test_the_channel_limit_can_be_overridden(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    result = imported_record(runner, wired, tmp_path, "--limit-ue", "9000", railed=True)
    assert "0.0% railed" in result.output


def test_a_gauge_that_is_not_in_the_book_is_refused(
    runner: CliRunner, wired: Path, tmp_path: Path
) -> None:
    strain = strain_file(tmp_path)
    result = runner.invoke(
        main,
        ["--book", str(wired), "record", CAMPAIGN, "nope", str(strain), "--rate-hz", "20"],
    )
    assert result.exit_code != 0
    assert "no gauge" in result.output


def test_a_wider_bin_gives_fewer_bins(runner: CliRunner, wired: Path, tmp_path: Path) -> None:
    narrow = imported_record(runner, wired, tmp_path, "--bin-width-ue", "2")
    wide = imported_record(runner, wired, tmp_path, "--bin-width-ue", "40")
    assert _bins(wide) < _bins(narrow)


def _bins(result: Any) -> int:
    line = next(line for line in result.output.splitlines() if line.startswith("cycles"))
    return int(line.split(" in ")[1].split()[0])
