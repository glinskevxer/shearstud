"""The docstring check, driven against planted defects as well as the real tree."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from shearstud.tools import check_docstrings as check
from shearstud.tools.walk import SourceFile

pytestmark = pytest.mark.tools

Plant = Callable[..., None]
Source = Callable[[str, str], SourceFile]


def test_the_real_tree_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_tree() -> None:
    assert check.main() == 0


def test_a_module_with_no_docstring_is_caught(source: Source, planted: Plant) -> None:
    planted(check, [source("bare.py", "x = 1\n")])
    found = check.problems()
    assert found
    assert "no module docstring" in found[0]


def test_a_function_with_no_docstring_is_caught(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                '''
                """A module that says something useful about itself."""


                def compute(value: float) -> float:
                    return value
                ''',
            )
        ],
    )
    found = check.problems()
    assert any("function compute has no docstring" in p for p in found)


def test_a_private_function_is_left_alone(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                '''
                """A module that says something useful about itself."""


                def _compute(value: float) -> float:
                    return value
                ''',
            )
        ],
    )
    assert check.problems() == []


def test_a_class_with_no_docstring_is_caught(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                '''
                """A module that says something useful about itself."""


                class Girder:
                    pass
                ''',
            )
        ],
    )
    assert any("class Girder has no docstring" in p for p in check.problems())


def test_a_public_method_with_no_docstring_is_caught(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                '''
                """A module that says something useful about itself."""


                class Girder:
                    """A girder line through one structural unit."""

                    def rate(self) -> float:
                        return 1.0
                ''',
            )
        ],
    )
    assert any("method rate has no docstring" in p for p in check.problems())


def test_a_dunder_method_is_left_alone(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                '''
                """A module that says something useful about itself."""


                class Girder:
                    """A girder line through one structural unit."""

                    def __len__(self) -> int:
                        return 0
                ''',
            )
        ],
    )
    assert check.problems() == []


def test_a_docstring_too_short_to_say_anything_is_caught(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                '''
                """A module that says something useful about itself."""


                def compute(value: float) -> float:
                    """Do it."""
                    return value
                ''',
            )
        ],
    )
    assert any("too short" in p for p in check.problems())


def test_a_docstring_that_restates_its_name_is_caught(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                '''
                """A module that says something useful about itself."""


                def section_modulus_bottom(value: float) -> float:
                    """The section modulus of the bottom."""
                    return value
                ''',
            )
        ],
    )
    assert any("restates its own name" in p for p in check.problems())


def test_a_docstring_that_adds_something_is_accepted(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                '''
                """A module that says something useful about itself."""


                def section_modulus_bottom(value: float) -> float:
                    """Elastic modulus referred to the extreme tension fibre."""
                    return value
                ''',
            )
        ],
    )
    assert check.problems() == []


def test_the_problem_names_the_file_and_the_line(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "geometry/x.py",
                '''
                """A module that says something useful about itself."""


                def compute(value: float) -> float:
                    return value
                ''',
            )
        ],
    )
    assert "geometry/x.py:4" in check.problems()[0]


def test_the_check_exits_one_when_something_is_wrong(
    source: Source, planted: Plant, capsys: pytest.CaptureFixture[str]
) -> None:
    planted(check, [source("bare.py", "x = 1\n")])
    assert check.main() == 1
    assert "check_docstrings" in capsys.readouterr().out


def test_the_restatement_rule_ignores_filler_words() -> None:
    assert check._restates("span_length", "The length of the span.")
    assert not check._restates("span_length", "Distance between bearing centres.")
