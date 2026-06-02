"""The constants check, and the three things it deliberately lets through."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from shearstud.tools import check_constants as check
from shearstud.tools.walk import SourceFile

pytestmark = pytest.mark.tools

Plant = Callable[..., None]
Source = Callable[[str, str], SourceFile]

HEAD = '"""A module that says something useful about itself."""'


def planted_body(
    source: Source, planted: Plant, body: str, where: str = "rating/x.py"
) -> list[str]:
    planted(check, [source(where, f"{HEAD}\n\n{body}\n")])
    return check.problems()


def test_the_real_tree_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_tree() -> None:
    assert check.main([]) == 0


def test_a_coefficient_in_an_expression_is_caught(source: Source, planted: Plant) -> None:
    found = planted_body(source, planted, "def rate(x: float) -> float:\n    return 1.35 * x")
    assert len(found) == 1
    assert "the literal 1.35 wants a name and a clause" in found[0]


def test_the_line_the_coefficient_is_on_is_reported(source: Source, planted: Plant) -> None:
    body = "def rate(x: float) -> float:\n    y = x\n    return 1.35 * y"
    found = planted_body(source, planted, body)
    assert ":5 " in found[0]


def test_a_module_level_constant_is_not_a_problem(source: Source, planted: Plant) -> None:
    # This is what the check is asking for, so it cannot then object to it.
    body = "LIVE_FACTOR = 1.35\n\n\ndef rate(x: float) -> float:\n    return LIVE_FACTOR * x"
    assert planted_body(source, planted, body) == []


def test_an_arithmetic_identity_is_not_a_coefficient(source: Source, planted: Plant) -> None:
    body = "def half(x: float) -> float:\n    return 0.5 * x + 1.0 - 0.0"
    assert planted_body(source, planted, body) == []


def test_a_percentage_denominator_is_not_a_coefficient(source: Source, planted: Plant) -> None:
    body = "def frac(pct: float) -> float:\n    return pct / 100.0"
    assert planted_body(source, planted, body) == []


def test_a_default_argument_is_not_a_coefficient(source: Source, planted: Plant) -> None:
    # A default is part of the signature. It shows in the help, in the
    # docstring and at every call site that overrides it, which is the whole
    # thing a named constant buys.
    body = "def rate(x: float, factor: float = 1.35) -> float:\n    return factor * x"
    assert planted_body(source, planted, body) == []


def test_a_default_used_again_in_the_body_is_not_reported(source: Source, planted: Plant) -> None:
    body = (
        "def rate(x: float, factor: float = 1.35) -> float:\n"
        "    if x < 0.0:\n"
        "        return 1.35\n"
        "    return factor * x"
    )
    assert planted_body(source, planted, body) == []


def test_a_negative_default_is_recognised(source: Source, planted: Plant) -> None:
    body = "def slope(x: float, m: float = -0.25) -> float:\n    return m * x + -0.25"
    assert planted_body(source, planted, body) == []


def test_the_sign_lives_in_the_operator_and_not_in_the_number(
    source: Source, planted: Plant
) -> None:
    # The parser puts a leading minus in a UnaryOp and the digits in the
    # constant, in a default and in an expression alike. Comparing the
    # constants is comparing like with like.
    body = "def slope(x: float, m: float = -0.25) -> float:\n    return m * x - 0.25"
    assert planted_body(source, planted, body) == []


def test_an_exempt_conversion_is_not_reported(source: Source, planted: Plant) -> None:
    body = "def inches(feet: float) -> float:\n    return feet * 12.0"
    assert planted_body(source, planted, body) == []


def test_an_integer_literal_is_not_reported(source: Source, planted: Plant) -> None:
    # Integers count things. The rule is about measurements.
    body = "def third(values: list[float]) -> float:\n    return values[3]"
    assert planted_body(source, planted, body) == []


def test_a_boolean_is_not_read_as_a_number(source: Source, planted: Plant) -> None:
    body = "def flag() -> bool:\n    return True"
    assert planted_body(source, planted, body) == []


def test_the_command_line_layer_is_not_checked(source: Source, planted: Plant) -> None:
    # A default belongs where the option is declared.
    body = "def rate(x: float) -> float:\n    return 1.35 * x"
    assert planted_body(source, planted, body, where="cli/x.py") == []


def test_the_tools_layer_is_not_checked(source: Source, planted: Plant) -> None:
    body = "def rate(x: float) -> float:\n    return 1.35 * x"
    assert planted_body(source, planted, body, where="tools/x.py") == []


def test_the_same_literal_twice_on_one_line_is_reported_once(
    source: Source, planted: Plant
) -> None:
    body = "def rate(x: float) -> float:\n    return 1.35 * x + 1.35"
    assert len(planted_body(source, planted, body)) == 1


def test_two_different_literals_on_one_line_are_both_reported(
    source: Source, planted: Plant
) -> None:
    body = "def rate(x: float) -> float:\n    return 1.35 * x + 0.77"
    assert len(planted_body(source, planted, body)) == 2


def test_the_literals_of_a_file_are_collected(source: Source) -> None:
    body = f"{HEAD}\n\nTOP = 9.9\n\n\ndef rate(x: float) -> float:\n    return 1.35 * x\n"
    found = check.literals(source("rating/x.py", body))
    assert [value for _, value in found] == [1.35]


def test_the_defaults_of_a_file_are_collected(source: Source) -> None:
    body = f"{HEAD}\n\n\ndef rate(x: float, factor: float = 1.35) -> float:\n    return x\n"
    assert check.defaults(source("rating/x.py", body)) == {1.35}


def test_a_keyword_only_default_is_collected(source: Source) -> None:
    body = f"{HEAD}\n\n\ndef rate(x: float, *, factor: float = 1.35) -> float:\n    return x\n"
    assert check.defaults(source("rating/x.py", body)) == {1.35}


def test_every_checked_layer_carries_some_arithmetic() -> None:
    # A layer that reports zero literals is a layer this check is not reaching,
    # which looks the same from outside as a layer with nothing to find.
    numbers = check.counts()
    assert set(numbers) == set(check.CHECKED_LAYERS)
    for layer, count in numbers.items():
        assert count > 0, layer


def test_the_counts_print_on_request(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main(["--counts"]) == 0
    out = capsys.readouterr().out
    assert "geometry carries" in out


def test_a_problem_is_reported_and_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(check, "problems", lambda: ["src/shearstud/rating/x.py:4 the literal 1.35"])
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert "check_constants: src/shearstud/rating/x.py:4" in out
    assert "1 problem(s)" in out


def test_no_exemption_is_also_an_identity() -> None:
    # Two lists that overlap are two lists where deleting from one does
    # nothing, which is how an exemption outlives its reason.
    assert frozenset() == check.IDENTITIES & check.EXEMPT_VALUES
