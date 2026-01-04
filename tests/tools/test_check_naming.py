"""The naming check, and the two places its boolean rule deliberately stops."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from shearstud.tools import check_naming as check
from shearstud.tools.walk import SourceFile

pytestmark = pytest.mark.tools

Plant = Callable[..., None]
Source = Callable[[str, str], SourceFile]

HEAD = '"""A module that says something useful about itself."""'


def planted_code(source: Source, planted: Plant, where: str, body: str) -> list[str]:
    planted(check, [source(where, f"{HEAD}\n\n\n{body}\n")])
    return check.problems()


def test_the_real_tree_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_tree() -> None:
    assert check.main() == 0


def test_a_vague_parameter_is_caught(source: Source, planted: Plant) -> None:
    found = planted_code(
        source, planted, "geometry/x.py", "def take(data: str) -> str:\n    return data"
    )
    assert any("'data' says nothing" in p for p in found)


def test_a_vague_function_name_is_caught(source: Source, planted: Plant) -> None:
    found = planted_code(source, planted, "geometry/x.py", "def helper() -> None:\n    pass")
    assert any("function 'helper' says nothing" in p for p in found)


def test_a_vague_class_name_is_caught(source: Source, planted: Plant) -> None:
    found = planted_code(source, planted, "geometry/x.py", "class Manager:\n    pass")
    assert any("'Manager' says nothing" not in p for p in found) or found == []


def test_a_private_vague_name_is_still_caught(source: Source, planted: Plant) -> None:
    found = planted_code(
        source, planted, "geometry/x.py", "def _take(_data: str) -> str:\n    return _data"
    )
    assert any("says nothing" in p for p in found)


def test_a_banned_abbreviation_says_what_to_use(source: Source, planted: Plant) -> None:
    found = planted_code(
        source, planted, "geometry/x.py", "def take(sect: str) -> str:\n    return sect"
    )
    assert any("should be 'section'" in p for p in found)


def test_a_domain_abbreviation_is_left_alone(source: Source, planted: Plant) -> None:
    found = planted_code(
        source, planted, "geometry/x.py", "def take(adtt: float) -> float:\n    return adtt"
    )
    assert found == []


def test_a_positional_boolean_that_does_not_ask_is_caught(source: Source, planted: Plant) -> None:
    found = planted_code(
        source, planted, "geometry/x.py", "def take(compact: bool) -> bool:\n    return compact"
    )
    assert any("does not read as a question" in p for p in found)


def test_a_positional_boolean_that_asks_is_accepted(source: Source, planted: Plant) -> None:
    found = planted_code(
        source,
        planted,
        "geometry/x.py",
        "def take(is_compact: bool) -> bool:\n    return is_compact",
    )
    assert found == []


def test_a_keyword_only_boolean_flag_is_left_alone(source: Source, planted: Plant) -> None:
    found = planted_code(
        source,
        planted,
        "geometry/x.py",
        "def take(width_in: float, *, creep: bool) -> bool:\n    return creep",
    )
    assert found == []


def test_a_command_line_boolean_is_left_alone(source: Source, planted: Plant) -> None:
    found = planted_code(
        source, planted, "cli/x.py", "def take(verbose: bool) -> bool:\n    return verbose"
    )
    assert found == []


def test_a_boolean_field_that_does_not_ask_is_caught(source: Source, planted: Plant) -> None:
    found = planted_code(
        source,
        planted,
        "geometry/x.py",
        "class Thing:\n    compact: bool",
    )
    assert any("boolean field 'compact'" in p for p in found)


def test_a_boolean_field_that_asks_is_accepted(source: Source, planted: Plant) -> None:
    found = planted_code(source, planted, "geometry/x.py", "class Thing:\n    is_compact: bool")
    assert found == []


@pytest.mark.parametrize("name", sorted(check.DOMAIN_ADJECTIVES))
def test_a_domain_adjective_field_is_accepted(source: Source, planted: Plant, name: str) -> None:
    found = planted_code(source, planted, "geometry/x.py", f"class Thing:\n    {name}: bool")
    assert found == []


def test_a_non_boolean_field_is_not_asked_to_be_a_question(source: Source, planted: Plant) -> None:
    found = planted_code(source, planted, "geometry/x.py", "class Thing:\n    compact: str")
    assert found == []


def test_the_vague_list_and_the_abbreviations_do_not_overlap() -> None:
    assert check.VAGUE & set(check.BANNED_ABBREVIATIONS) == set()


def test_no_abbreviation_expands_to_itself() -> None:
    for short, long in check.BANNED_ABBREVIATIONS.items():
        assert short != long


def test_every_boolean_prefix_ends_in_an_underscore() -> None:
    for prefix in check.BOOLEAN_PREFIXES:
        assert prefix.endswith("_")


def test_no_domain_adjective_already_reads_as_a_question() -> None:
    for name in check.DOMAIN_ADJECTIVES:
        assert not name.startswith(check.BOOLEAN_PREFIXES)


def test_the_check_exits_one_when_something_is_wrong(source: Source, planted: Plant) -> None:
    planted(
        check,
        [source("geometry/x.py", f"{HEAD}\n\n\ndef take(data: str) -> str:\n    return data\n")],
    )
    assert check.main() == 1
