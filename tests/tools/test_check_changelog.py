"""The changelog check, driven against synthetic documents."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from shearstud import __version__
from shearstud.tools import check_changelog as check

pytestmark = pytest.mark.tools

CLEAN = """# Changelog

## 9.9.9 - 2026-05-01

### Added

- Something.

## 9.9.8 - 2026-04-01

### Fixed

- **Changes results.** Something that moved a number.
"""


@pytest.fixture
def planted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):  # type: ignore[no-untyped-def]
    """Point the check at a changelog written for the test."""

    def plant(text: str, version: str = "9.9.9", declared: str | None = None) -> list[str]:
        path = tmp_path / "CHANGELOG.md"
        path.write_text(text, encoding="utf-8")
        monkeypatch.setattr(check, "CHANGELOG", path)
        monkeypatch.setattr(check, "__version__", version)
        monkeypatch.setattr(check, "declared_version", lambda: declared or version)
        return check.problems()

    return plant


def test_the_real_changelog_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_tree() -> None:
    assert check.main([]) == 0


def test_the_newest_entry_is_the_version_the_package_reports() -> None:
    assert check.releases()[0][0] == __version__


def test_the_packaging_metadata_agrees_with_the_package() -> None:
    assert check.declared_version() == __version__


def test_every_release_carries_a_date() -> None:
    assert all(isinstance(when, date) for _, when in check.releases())


def test_the_real_entries_run_newest_first() -> None:
    dates = [when for _, when in check.releases()]
    assert dates == sorted(dates, reverse=True)


def test_a_clean_document_has_no_problems(planted) -> None:  # type: ignore[no-untyped-def]
    assert planted(CLEAN) == []


def test_a_version_that_does_not_match_the_package_is_caught(planted) -> None:  # type: ignore[no-untyped-def]
    found = planted(CLEAN, version="9.9.7")
    assert any("the newest entry is 9.9.9" in problem for problem in found)


def test_packaging_metadata_that_disagrees_is_caught(planted) -> None:  # type: ignore[no-untyped-def]
    found = planted(CLEAN, declared="1.2.3")
    assert any("pyproject says 1.2.3" in problem for problem in found)


def test_entries_out_of_order_are_caught(planted) -> None:  # type: ignore[no-untyped-def]
    text = CLEAN.replace("## 9.9.9 - 2026-05-01", "## 9.9.9 - 2026-03-01")
    found = planted(text)
    assert any("before 9.9.8" in problem for problem in found)


def test_two_entries_for_one_version_are_caught(planted) -> None:  # type: ignore[no-untyped-def]
    text = CLEAN + "\n## 9.9.9 - 2026-01-01\n\n### Added\n\n- Again.\n"
    found = planted(text)
    assert any("more than one entry" in problem for problem in found)


def test_a_release_with_no_sections_is_caught(planted) -> None:  # type: ignore[no-untyped-def]
    text = "# Changelog\n\n## 9.9.9 - 2026-05-01\n\n- A bare bullet.\n"
    found = planted(text)
    assert any("9.9.9 has no sections" in problem for problem in found)


def test_a_section_heading_nobody_uses_is_caught(planted) -> None:  # type: ignore[no-untyped-def]
    text = CLEAN.replace("### Added", "### Miscellaneous")
    found = planted(text)
    assert any("'Miscellaneous' section" in problem for problem in found)


def test_a_fix_that_does_not_say_it_moved_a_number_is_caught(planted) -> None:  # type: ignore[no-untyped-def]
    text = CLEAN.replace("**Changes results.** Something that moved a number.", "Something.")
    found = planted(text)
    assert any("and no entry says" in problem for problem in found)


def test_a_release_with_no_fixes_needs_no_mark(planted) -> None:  # type: ignore[no-untyped-def]
    text = "# Changelog\n\n## 9.9.9 - 2026-05-01\n\n### Added\n\n- Something.\n"
    assert planted(text) == []


def test_a_document_with_no_releases_is_caught(planted) -> None:  # type: ignore[no-untyped-def]
    found = planted("# Changelog\n\nNothing has happened yet.\n")
    assert found == ["no release headings, expected '## <version> - <date>'"]


def test_a_missing_changelog_is_one_problem(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "CHANGELOG", Path("nowhere") / "CHANGELOG.md")
    assert check.problems() == ["there is no CHANGELOG.md"]
    assert check.releases() == []


def test_the_sections_of_a_release_are_read(planted) -> None:  # type: ignore[no-untyped-def]
    planted(CLEAN)
    assert check.sections_of("9.9.9") == ["Added"]
    assert check.sections_of("9.9.8") == ["Fixed"]


def test_asking_for_a_release_that_is_not_there_gives_nothing(planted) -> None:  # type: ignore[no-untyped-def]
    planted(CLEAN)
    assert check.sections_of("1.0.0") == []
    assert check.body_of("1.0.0") == ""


def test_the_body_of_a_release_stops_at_the_next_one(planted) -> None:  # type: ignore[no-untyped-def]
    planted(CLEAN)
    assert "Something." in check.body_of("9.9.9")
    assert "moved a number" not in check.body_of("9.9.9")


def test_the_listing_prints_what_it_found(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main(["--list"]) == 0
    assert f"check_changelog: {__version__}" in capsys.readouterr().out


def test_a_problem_is_reported_and_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(check, "problems", lambda: ["says something untrue"])
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert "check_changelog: says something untrue" in out
    assert "1 problem(s)" in out
