"""The frozen dataclass rule, and the one exception it does not reach."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from shearstud.tools import check_dataclasses as check
from shearstud.tools.walk import SourceFile

pytestmark = pytest.mark.tools

Plant = Callable[..., None]
Source = Callable[[str, str], SourceFile]

HEAD = '"""A module that says something useful about itself."""'


def planted_class(source: Source, planted: Plant, body: str) -> list[str]:
    planted(
        check, [source("rating/x.py", f"{HEAD}\n\nfrom dataclasses import dataclass\n\n\n{body}\n")]
    )
    return check.problems()


def test_the_real_tree_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_tree() -> None:
    assert check.main([]) == 0


def test_a_frozen_dataclass_with_slots_passes(source: Source, planted: Plant) -> None:
    body = "@dataclass(frozen=True, slots=True)\nclass Verdict:\n    value: float"
    assert planted_class(source, planted, body) == []


def test_a_mutable_dataclass_is_caught(source: Source, planted: Plant) -> None:
    body = "@dataclass\nclass Verdict:\n    value: float"
    found = planted_class(source, planted, body)
    assert any("without frozen=True" in problem for problem in found)
    assert any("without slots=True" in problem for problem in found)


def test_a_dataclass_that_is_not_frozen_is_caught(source: Source, planted: Plant) -> None:
    body = "@dataclass(slots=True)\nclass Verdict:\n    value: float"
    found = planted_class(source, planted, body)
    assert len(found) == 1
    assert "without frozen=True" in found[0]


def test_a_dataclass_with_no_slots_is_caught(source: Source, planted: Plant) -> None:
    body = "@dataclass(frozen=True)\nclass Verdict:\n    value: float"
    found = planted_class(source, planted, body)
    assert len(found) == 1
    assert "without slots=True" in found[0]


def test_frozen_written_as_false_is_caught(source: Source, planted: Plant) -> None:
    body = "@dataclass(frozen=False, slots=True)\nclass Verdict:\n    value: float"
    found = planted_class(source, planted, body)
    assert any("without frozen=True" in problem for problem in found)


def test_a_qualified_decorator_is_recognised(source: Source, planted: Plant) -> None:
    body = "@dataclasses.dataclass(frozen=True, slots=True)\nclass Verdict:\n    value: float"
    assert planted_class(source, planted, body) == []


def test_a_qualified_bare_decorator_is_caught(source: Source, planted: Plant) -> None:
    body = "@dataclasses.dataclass\nclass Verdict:\n    value: float"
    assert planted_class(source, planted, body) != []


def test_a_plain_class_is_not_the_checks_business(source: Source, planted: Plant) -> None:
    body = "class Verdict:\n    value: float = 0.0"
    assert planted_class(source, planted, body) == []


def test_another_decorator_is_not_read_as_a_dataclass(source: Source, planted: Plant) -> None:
    body = "@click.group()\nclass Verdict:\n    value: float"
    assert planted_class(source, planted, body) == []


def test_the_class_and_its_line_are_reported(source: Source, planted: Plant) -> None:
    body = "@dataclass(frozen=True)\nclass Verdict:\n    value: float"
    found = planted_class(source, planted, body)
    assert "Verdict" in found[0]
    assert "rating/x.py:" in found[0]


def test_the_dataclasses_of_a_file_are_collected(source: Source) -> None:
    body = (
        f"{HEAD}\n\nfrom dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True, slots=True)\nclass A:\n    x: float\n\n\n"
        "@dataclass(frozen=True, slots=True)\nclass B:\n    y: float\n"
    )
    assert [node.name for node in check.dataclasses_in(source("rating/x.py", body))] == ["A", "B"]


def test_the_keywords_of_a_decorator_are_read(source: Source) -> None:
    body = (
        f"{HEAD}\n\nfrom dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True, slots=False, order=True)\nclass A:\n    x: float\n"
    )
    node = check.dataclasses_in(source("rating/x.py", body))[0]
    assert check.keywords_of(node) == {"frozen": True, "slots": False, "order": True}


def test_a_bare_decorator_carries_no_keywords(source: Source) -> None:
    body = f"{HEAD}\n\nfrom dataclasses import dataclass\n\n\n@dataclass\nclass A:\n    x: float\n"
    node = check.dataclasses_in(source("rating/x.py", body))[0]
    assert check.keywords_of(node) == {}


def test_every_application_layer_declares_some_values() -> None:
    # A layer with no dataclasses is a layer this check is not reaching, which
    # looks the same from outside as a layer with nothing to find.
    numbers = check.counts()
    for layer in ("geometry", "loads", "signals", "fatigue", "structure", "rating", "store"):
        assert numbers.get(layer, 0) > 0, layer


def test_the_walker_is_the_one_exception_and_it_is_in_the_tools() -> None:
    # cached_property stores into the instance dictionary and there is not one
    # under slots. The tools are outside what this check walks.
    from shearstud.tools.walk import SourceFile as Walked

    assert not hasattr(Walked, "__slots__")
    assert "tools" not in check.counts()


def test_the_counts_print_on_request(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main(["--counts"]) == 0
    assert "geometry declares" in capsys.readouterr().out


def test_a_problem_is_reported_and_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(check, "problems", lambda: ["rating/x.py:4 Verdict is a dataclass"])
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert "check_dataclasses: rating/x.py:4" in out
    assert "1 problem(s)" in out
