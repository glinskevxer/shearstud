"""The README check, and the two ways it could quietly stop checking."""

from __future__ import annotations

import pytest

from shearstud.tools import check_readme as check

pytestmark = pytest.mark.tools

FENCE = "```"


def document(body: str) -> str:
    """A README fragment with one fenced block in it."""
    return f"{FENCE}\n{body}\n{FENCE}\n"


def test_the_real_readme_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_readme() -> None:
    assert check.main([]) == 0


def test_a_real_command_is_accepted() -> None:
    assert check.unknown_commands(document("shearstud structure list")) == []


def test_a_command_that_does_not_exist_is_caught() -> None:
    assert check.unknown_commands(document("shearstud frobnicate 18-SH-0473")) == [
        "frobnicate 18-SH-0473"
    ]


def test_a_subcommand_that_does_not_exist_is_caught() -> None:
    assert check.unknown_commands(document("shearstud structure frobnicate")) == [
        "structure frobnicate"
    ]


def test_the_book_option_and_its_value_are_stepped_over() -> None:
    # The option takes a value, so a naive scan reads the path as a command.
    found = check.command_path(["--book", "/tmp/x.sqlite3", "structure", "list"])
    assert found == ["structure", "list"]


def test_a_flag_with_no_value_is_stepped_over() -> None:
    assert check.command_path(["rate", "--save"]) == ["rate"]


def test_the_arguments_after_a_command_are_not_read_as_commands() -> None:
    assert check.command_path(["rate", "18-SH-0473", "--save"]) == ["rate"]


def test_a_bare_help_invocation_is_not_a_missing_command() -> None:
    assert check.unknown_commands(document("shearstud --help")) == []


def test_a_line_outside_a_fenced_block_is_not_read_as_a_command() -> None:
    assert check.unknown_commands("Run shearstud frobnicate to do the thing.\n") == []


def test_every_command_line_in_the_document_is_found() -> None:
    body = document("shearstud init\nshearstud structure list\ncd /tmp")
    assert check.invocations(body) == [["init"], ["structure", "list"]]


def test_a_missing_heading_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "REQUIRED_HEADINGS", ("## Nowhere",))
    assert any("'## Nowhere'" in problem for problem in check.problems())


def test_a_link_to_a_file_that_is_there_is_accepted() -> None:
    assert "docs/schema.md" in check.linked_paths("[the schema](docs/schema.md)")


def test_a_backticked_file_name_is_read_as_a_path() -> None:
    assert "migrations.lock" in check.linked_paths("the digests are in `migrations.lock`")


def test_a_backticked_command_is_not_read_as_a_path() -> None:
    assert check.linked_paths("run `shearstud init` first") == []


def test_a_link_to_a_file_that_is_not_there_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "linked_paths", lambda _text: ["docs/nowhere.md"])
    assert any("docs/nowhere.md" in problem for problem in check.problems())


def test_a_web_link_is_not_looked_for_on_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "linked_paths", lambda _text: ["https://example.invalid/x"])
    assert check.problems() == []


def test_the_supported_versions_are_actually_declared() -> None:
    # Without this the version check is inert: an empty set passes silently,
    # and a check that cannot fail is worse than no check.
    assert check.python_versions() == {"3.12", "3.13"}


def test_an_undeclared_version_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check, "python_versions", lambda: {"3.14"})
    assert any("Python 3.14" in problem for problem in check.problems())


def test_a_missing_readme_is_one_problem_and_not_twenty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    from pathlib import Path

    monkeypatch.setattr(check, "README", Path("nowhere") / "README.md")
    assert check.problems() == ["there is no README.md"]


def test_the_listing_prints_what_it_found(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "check_readme: init" in out


def test_a_problem_is_reported_and_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(check, "problems", lambda: ["says something untrue"])
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert "check_readme: says something untrue" in out
    assert "1 problem(s)" in out


def test_the_word_that_is_not_a_command_is_the_one_reported() -> None:
    assert check.resolve(["structure", "frobnicate"]) == (["structure"], "frobnicate")


def test_an_argument_to_a_leaf_command_is_not_reported() -> None:
    assert check.resolve(["rate", "18-SH-0473"]) == (["rate"], None)


def test_a_fully_resolved_group_and_command_reports_nothing_missing() -> None:
    assert check.resolve(["program", "worklist"]) == (["program", "worklist"], None)
