"""The wiring check, and the three ways it deliberately looks the other way."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from shearstud.tools import check_wiring as check
from shearstud.tools.walk import SourceFile

pytestmark = pytest.mark.tools

Plant = Callable[..., None]
Source = Callable[[str, str], SourceFile]

HEAD = '"""A module that says something useful about itself."""'

#: A result class and the function that builds it, the shape the carve out is
#: written for.
RESULT_CLASS = "class Verdict:\n    pass\n\n\ndef decide() -> Verdict:\n    return Verdict()\n"


def plant_tree(planted: Plant, files: list[SourceFile], suite: list[SourceFile]) -> list[str]:
    """Point the check at a whole synthetic world, source and tests both."""
    planted(check, files)
    planted(check, suite, "suite_files")
    return check.problems()


def test_the_real_tree_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_tree() -> None:
    assert check.main([]) == 0


def test_a_function_nothing_mentions_is_caught(
    source: Source, suite: Source, planted: Plant
) -> None:
    found = plant_tree(
        planted,
        [source("rating/x.py", f"{HEAD}\n\n\ndef unloved() -> int:\n    return 1\n")],
        [suite("test_y.py", f"{HEAD}\n\n\ndef test_nothing() -> None:\n    assert True\n")],
    )
    assert found == ["src/shearstud/rating/x.py:4 function unloved has no caller and no test"]


def test_a_function_another_module_calls_is_left_alone(
    source: Source, suite: Source, planted: Plant
) -> None:
    found = plant_tree(
        planted,
        [
            source("rating/x.py", f"{HEAD}\n\n\ndef wanted() -> int:\n    return 1\n"),
            source("cli/y.py", f"{HEAD}\n\nfrom shearstud.rating.x import wanted\n"),
        ],
        [suite("test_y.py", f"{HEAD}\n\n\ndef test_nothing() -> None:\n    assert True\n")],
    )
    assert found == []


def test_a_function_only_a_test_names_is_left_alone(
    source: Source, suite: Source, planted: Plant
) -> None:
    found = plant_tree(
        planted,
        [source("rating/x.py", f"{HEAD}\n\n\ndef wanted() -> int:\n    return 1\n")],
        [suite("test_x.py", f"{HEAD}\n\n\ndef test_it() -> None:\n    assert wanted() == 1\n")],
    )
    assert found == []


def test_a_name_used_only_in_its_own_module_is_still_caught(
    source: Source, suite: Source, planted: Plant
) -> None:
    body = (
        f"{HEAD}\n\n\ndef helper() -> int:\n    return 1\n\n\n"
        "def other() -> int:\n    return helper()\n"
    )
    found = plant_tree(
        planted,
        [
            source("rating/x.py", body),
            source("cli/y.py", f"{HEAD}\n\nfrom shearstud.rating.x import other\n"),
        ],
        [suite("test_y.py", f"{HEAD}\n\n\ndef test_nothing() -> None:\n    assert True\n")],
    )
    assert any("function helper" in problem for problem in found)
    assert not any("function other" in problem for problem in found)


def test_a_private_function_is_not_the_checks_business(
    source: Source, suite: Source, planted: Plant
) -> None:
    found = plant_tree(
        planted,
        [source("rating/x.py", f"{HEAD}\n\n\ndef _quiet() -> int:\n    return 1\n")],
        [suite("test_y.py", f"{HEAD}\n\n\ndef test_nothing() -> None:\n    assert True\n")],
    )
    assert found == []


def test_a_decorated_function_is_taken_as_registered(
    source: Source, suite: Source, planted: Plant
) -> None:
    body = f"{HEAD}\n\nimport click\n\n\n@click.command()\ndef prune() -> None:\n    pass\n"
    found = plant_tree(
        planted,
        [source("cli/x.py", body)],
        [suite("test_y.py", f"{HEAD}\n\n\ndef test_nothing() -> None:\n    assert True\n")],
    )
    assert found == []


def test_a_class_something_returns_is_taken_as_reachable(
    source: Source, suite: Source, planted: Plant
) -> None:
    body = f"{HEAD}\n\n\n{RESULT_CLASS}"
    found = plant_tree(
        planted,
        [
            source("rating/x.py", body),
            source("cli/y.py", f"{HEAD}\n\nfrom shearstud.rating.x import decide\n"),
        ],
        [suite("test_y.py", f"{HEAD}\n\n\ndef test_nothing() -> None:\n    assert True\n")],
    )
    assert found == []


def test_the_function_behind_an_unreachable_result_class_is_still_caught(
    source: Source, suite: Source, planted: Plant
) -> None:
    # The carve out for result types would be a hole if it hid the factory too.
    body = f"{HEAD}\n\n\n{RESULT_CLASS}"
    found = plant_tree(
        planted,
        [source("rating/x.py", body)],
        [suite("test_y.py", f"{HEAD}\n\n\ndef test_nothing() -> None:\n    assert True\n")],
    )
    assert found == ["src/shearstud/rating/x.py:8 function decide has no caller and no test"]


def test_a_method_nothing_reaches_for_is_caught(
    source: Source, suite: Source, planted: Plant
) -> None:
    body = f"{HEAD}\n\n\nclass Thing:\n    def dusty(self) -> int:\n        return 1\n"
    found = plant_tree(
        planted,
        [
            source("rating/x.py", body),
            source("cli/y.py", f"{HEAD}\n\nfrom shearstud.rating.x import Thing\n"),
        ],
        [suite("test_y.py", f"{HEAD}\n\n\ndef test_nothing() -> None:\n    assert True\n")],
    )
    assert any("method dusty" in problem for problem in found)


def test_a_method_reached_by_attribute_is_left_alone(
    source: Source, suite: Source, planted: Plant
) -> None:
    body = f"{HEAD}\n\n\nclass Thing:\n    def used(self) -> int:\n        return 1\n"
    caller = f"{HEAD}\n\nfrom shearstud.rating.x import Thing\n\nVALUE = Thing().used()\n"
    found = plant_tree(
        planted,
        [source("rating/x.py", body), source("cli/y.py", caller)],
        [suite("test_y.py", f"{HEAD}\n\n\ndef test_nothing() -> None:\n    assert True\n")],
    )
    assert found == []


def test_the_entry_point_name_is_never_reported(
    source: Source, suite: Source, planted: Plant
) -> None:
    found = plant_tree(
        planted,
        [source("cli/x.py", f"{HEAD}\n\n\ndef main() -> int:\n    return 0\n")],
        [suite("test_y.py", f"{HEAD}\n\n\ndef test_nothing() -> None:\n    assert True\n")],
    )
    assert found == []


def test_the_names_a_file_uses_include_attributes_and_imports(source: Source) -> None:
    body = f"{HEAD}\n\nfrom shearstud.rating.x import wanted\n\nVALUE = wanted().field\n"
    names = check.used_names(source("cli/y.py", body))
    assert {"wanted", "field"} <= names


def test_the_returned_types_of_a_file_are_collected(source: Source) -> None:
    body = f"{HEAD}\n\n\ndef decide() -> list[Verdict] | None:\n    return None\n"
    assert "Verdict" in check.returned_types(source("rating/x.py", body))


def test_a_file_that_returns_nothing_declares_no_types(source: Source) -> None:
    body = f"{HEAD}\n\n\ndef decide():\n    return None\n"
    assert check.returned_types(source("rating/x.py", body)) == set()


def test_the_vocabulary_says_which_file_used_a_name() -> None:
    seen = check.vocabulary()
    assert any("influence" in where for where in seen["simple_moment"])


def test_the_softer_question_is_asked_separately() -> None:
    # Something wired but never named by a test is a different report, and it
    # does not fail the check.
    assert isinstance(check.unexercised(), list)
    assert check.main([]) == 0


def test_the_unexercised_list_prints_on_request(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main(["--unexercised"]) == 0
    out = capsys.readouterr().out
    assert "check_wiring: clean" in out


def test_a_problem_is_reported_and_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(check, "problems", lambda: ["src/shearstud/rating/x.py:4 function gone"])
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert "check_wiring: src/shearstud/rating/x.py:4 function gone" in out
    assert "1 problem(s)" in out
