"""The migration lock, and the four ways it can disagree with the code."""

from __future__ import annotations

from pathlib import Path

import pytest

from shearstud.errors import ConfigError
from shearstud.tools import build_lock
from shearstud.tools import check_migrations as check

pytestmark = pytest.mark.tools


def test_the_lock_on_disk_matches_the_code() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_when_the_lock_is_current() -> None:
    assert check.main() == 0


def test_the_lock_file_is_where_it_says_it_is() -> None:
    assert check.LOCK_PATH.name == "migrations.lock"
    assert check.LOCK_PATH.exists()


def test_every_migration_is_locked() -> None:
    from shearstud.store import migrate

    locked = {line.version for line in check.read_lock()}
    assert locked == {int(m.VERSION) for m in migrate.available()}


def test_each_digest_is_a_full_length_hash() -> None:
    for line in check.read_lock():
        assert len(line.digest) == 64


def test_comments_and_blanks_are_dropped() -> None:
    text = "# a comment\n\n001 structures " + "a" * 64 + "\n"
    lines = check.parse_lock(text)
    assert len(lines) == 1
    assert lines[0].name == "structures"


def test_a_line_with_the_wrong_field_count_is_refused() -> None:
    with pytest.raises(ConfigError, match="expected version, name, digest"):
        check.parse_lock("001 structures\n")


def test_a_line_with_a_bad_version_is_refused() -> None:
    with pytest.raises(ConfigError, match="is not a version"):
        check.parse_lock("first structures " + "a" * 64 + "\n")


def test_a_missing_lock_is_reported(tmp_path: Path) -> None:
    found = check.problems(tmp_path / "gone.lock")
    assert found
    assert "no gone.lock" in found[0]


def test_reading_a_missing_lock_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="no gone.lock"):
        check.read_lock(tmp_path / "gone.lock")


def test_an_edited_migration_is_caught(tmp_path: Path) -> None:
    path = tmp_path / "migrations.lock"
    lines = check.expected_lines()
    body = [f"{line.version:03d} {line.name} {line.digest}" for line in lines]
    body[1] = f"{lines[1].version:03d} {lines[1].name} {'0' * 64}"
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    found = check.problems(path)
    assert any("has been edited since it was locked" in p for p in found)


def test_a_renamed_migration_is_caught(tmp_path: Path) -> None:
    path = tmp_path / "migrations.lock"
    lines = check.expected_lines()
    body = [f"{line.version:03d} {line.name} {line.digest}" for line in lines]
    body[0] = f"{lines[0].version:03d} inventory {lines[0].digest}"
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    found = check.problems(path)
    assert any("in the code and 'inventory' in the lock" in p for p in found)


def test_a_migration_missing_from_the_lock_is_caught(tmp_path: Path) -> None:
    path = tmp_path / "migrations.lock"
    lines = check.expected_lines()[:-1]
    body = [f"{line.version:03d} {line.name} {line.digest}" for line in lines]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    found = check.problems(path)
    assert any("is not in the lock" in p for p in found)


def test_a_lock_entry_the_code_does_not_have_is_caught(tmp_path: Path) -> None:
    path = tmp_path / "migrations.lock"
    body = [f"{line.version:03d} {line.name} {line.digest}" for line in check.expected_lines()]
    body.append("009 imaginary " + "a" * 64)
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    found = check.problems(path)
    assert any("the lock has migration 9 and the code does not" in p for p in found)


def test_the_generated_text_round_trips() -> None:
    lines = check.parse_lock(check.lock_text())
    assert lines == check.expected_lines()


def test_the_generated_text_says_how_to_regenerate_it() -> None:
    assert "build_lock" in check.lock_text()


def test_the_generated_text_ends_in_a_newline() -> None:
    assert check.lock_text().endswith("\n")


def test_writing_a_current_lock_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "migrations.lock"
    assert build_lock.write(path) is True
    assert build_lock.write(path) is False


def test_a_written_lock_reads_as_current(tmp_path: Path) -> None:
    path = tmp_path / "migrations.lock"
    build_lock.write(path)
    assert build_lock.is_current(path)
    assert check.problems(path) == []


def test_a_missing_lock_is_not_current(tmp_path: Path) -> None:
    assert not build_lock.is_current(tmp_path / "gone.lock")


def test_the_builder_reports_that_the_shipped_lock_is_current(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert build_lock.main(["--check"]) == 0
    assert "is current" in capsys.readouterr().out
