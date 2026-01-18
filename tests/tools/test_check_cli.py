"""The command line documentation check, driven against the built tree."""

from __future__ import annotations

import click
import pytest

from shearstud.tools import check_cli as check

pytestmark = pytest.mark.tools


def test_the_real_command_line_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_tree() -> None:
    assert check.main() == 0


def test_every_command_the_package_ships_is_found() -> None:
    paths = check.command_paths()
    for expected in ("main init", "main rate", "main structure import", "main fatigue evaluate"):
        assert expected in paths


def test_the_paths_come_back_sorted() -> None:
    paths = check.command_paths()
    assert paths == sorted(paths)


def test_the_group_itself_is_not_listed_as_a_leaf() -> None:
    assert "" not in check.command_paths()


def test_every_command_has_a_help_line() -> None:
    for path, text in check.command_help().items():
        assert text.strip(), path


def test_the_help_lines_are_sentences_not_names() -> None:
    for path, text in check.command_help().items():
        assert len(text) >= check.MIN_HELP_CHARS, path


def test_a_command_with_no_help_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    @click.group()
    def bare() -> None:
        pass

    @bare.command()
    def silent() -> None:
        pass

    monkeypatch.setattr(check, "_command_tree", lambda: [("bare silent", silent)])
    assert any("has no help" in p for p in check.problems())


def test_a_help_line_too_short_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    @click.command()
    def terse() -> None:
        """Do it."""

    monkeypatch.setattr(check, "_command_tree", lambda: [("bare terse", terse)])
    assert any("too short" in p for p in check.problems())


def test_an_option_with_no_help_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    @click.command()
    @click.option("--loud", is_flag=True)
    def talkative(loud: bool) -> None:
        """Say what it is going to do before doing it."""

    monkeypatch.setattr(check, "_command_tree", lambda: [("bare talkative", talkative)])
    assert any("option --loud has no help" in p for p in check.problems())


def test_the_built_in_help_option_is_not_asked_for_help(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @click.command()
    def plain() -> None:
        """Say what it is going to do before doing it."""

    monkeypatch.setattr(check, "_command_tree", lambda: [("bare plain", plain)])
    assert check.problems() == []


def test_a_delete_with_no_confirmation_flag_is_caught(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @click.command("delete")
    def remove() -> None:
        """Take the structure out of the book of record."""

    monkeypatch.setattr(check, "_command_tree", lambda: [("bare delete", remove)])
    assert any("no way to say yes" in p for p in check.problems())


def test_a_delete_with_a_yes_flag_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    @click.command("delete")
    @click.option("--yes", is_flag=True, help="Do not ask before removing anything.")
    def remove(yes: bool) -> None:
        """Take the structure out of the book of record."""

    monkeypatch.setattr(check, "_command_tree", lambda: [("bare delete", remove)])
    assert check.problems() == []


def test_a_delete_with_a_force_flag_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    @click.command("prune")
    @click.option("--force", is_flag=True, help="Do not ask before removing anything.")
    def cut(force: bool) -> None:
        """Remove the runs that are older than the retention policy."""

    monkeypatch.setattr(check, "_command_tree", lambda: [("bare prune", cut)])
    assert check.problems() == []


def test_the_shipped_delete_command_offers_a_flag() -> None:
    tree = dict(check._command_tree())
    delete = tree["main structure delete"]
    names = {param.name for param in delete.params if param.name is not None}
    assert check.CONFIRM_FLAGS & names


def test_the_confirmation_flags_are_short_words() -> None:
    for flag in check.CONFIRM_FLAGS:
        assert flag.islower()
        assert "-" not in flag


def test_the_check_exits_one_when_something_is_wrong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @click.command()
    def silent() -> None:
        pass

    monkeypatch.setattr(check, "_command_tree", lambda: [("bare silent", silent)])
    assert check.main() == 1
