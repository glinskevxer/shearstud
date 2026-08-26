"""The command reference, built from the tree that ships rather than the source."""

from __future__ import annotations

import pytest

from shearstud.tools import build_commands as build

pytestmark = pytest.mark.tools


def test_the_shipped_document_is_current() -> None:
    assert build.DOCUMENT.is_current(build.body())


def test_the_check_exits_zero_when_the_document_is_current() -> None:
    assert build.main(["--check"]) == 0


def test_every_leaf_command_is_listed() -> None:
    listed = {row[0] for row in build.command_rows()}
    for expected in ("`init`", "`rate`", "`structure import`", "`fatigue evaluate`"):
        assert expected in listed


def test_the_groups_are_listed_separately() -> None:
    groups = {row[0] for row in build.group_rows()}
    assert "`structure`" in groups
    assert "`gauge`" in groups


def test_a_group_is_not_also_a_command() -> None:
    commands = {row[0] for row in build.command_rows()}
    groups = {row[0] for row in build.group_rows()}
    assert commands & groups == set()


def test_the_top_level_group_is_not_listed() -> None:
    listed = {row[0] for row in build.command_rows()} | {row[0] for row in build.group_rows()}
    assert "`main`" not in listed
    assert "``" not in listed


def test_the_rows_are_sorted() -> None:
    rows = build.command_rows()
    assert rows == sorted(rows)


def test_every_command_row_carries_a_description() -> None:
    for name, text in build.command_rows():
        assert text.strip(), name


def test_every_command_gets_a_detail_section() -> None:
    text = build.body()
    for name, _ in build.command_rows():
        heading = f"### `shearstud {name.strip('`')}`"
        assert heading in text


def test_the_detail_sections_list_the_options() -> None:
    text = build.body()
    assert "--stations" in text
    assert "--overlay" in text


def test_the_detail_sections_name_the_arguments() -> None:
    text = build.body()
    assert "Takes `number`" in text


def test_the_help_and_version_options_are_left_out() -> None:
    # The option rows and not the whole document. This used to search the
    # text, which convicted a command whose docstring mentioned --version in
    # a sentence, and the docstring was right.
    for line in build.body().splitlines():
        if not line.startswith("| `--"):
            continue
        option = line.split("`")[1]
        assert option not in ("--help", "--version"), line


def test_the_book_option_is_explained_once_at_the_top() -> None:
    text = build.body()
    assert "--book" in text.split("## Groups")[0]


def test_a_flag_with_no_default_shows_no_default() -> None:
    rows = [line for line in build.body().splitlines() if "--verbose" in line]
    assert rows
    assert "True" not in rows[0]


def test_an_option_with_a_default_shows_it() -> None:
    rows = [line for line in build.body().splitlines() if "--stations" in line]
    assert rows
    assert "`10`" in rows[0]


def test_the_document_names_the_command_that_wrote_it() -> None:
    assert "build_commands" in build.DOCUMENT.wrap(build.body())
