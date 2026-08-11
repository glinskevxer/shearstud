"""The example check, and what three separate things depend on the example for."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from shearstud.store import importer
from shearstud.tools import check_examples as check

pytestmark = pytest.mark.tools


def planted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, document: dict[str, Any]) -> list[str]:
    """Point the check at one document written for the test."""
    (tmp_path / "planted.json").write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(check, "EXAMPLES", tmp_path)
    return check.problems()


def shipped() -> dict[str, Any]:
    """The real example as a document, to alter one thing at a time."""
    document: dict[str, Any] = json.loads(
        (check.EXAMPLES / "salt-fork-creek.json").read_text(encoding="utf-8")
    )
    return document


def test_the_shipped_examples_are_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_tree() -> None:
    assert check.main([]) == 0


def test_there_is_at_least_one_example() -> None:
    assert check.documents()


def test_the_example_imports() -> None:
    # The README tells a new reader to import it, so it importing is the
    # first thing anybody depends on.
    structure = importer.read(check.documents()[0])
    assert str(structure.number) == "18-SH-0473"


def test_the_example_has_enough_girders() -> None:
    structure = importer.read(check.documents()[0])
    assert structure.girder_count >= check.MIN_GIRDERS


def test_the_example_has_more_than_one_detail_category() -> None:
    structure = importer.read(check.documents()[0])
    categories = {detail.category_name for detail in structure.details()}
    assert len(categories) >= check.MIN_CATEGORIES


def test_the_example_has_the_category_the_stringers_are_limited_by() -> None:
    structure = importer.read(check.documents()[0])
    categories = {detail.category_name for detail in structure.details()}
    assert check.WORST_CATEGORY in categories


def test_a_directory_with_no_examples_is_caught(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(check, "EXAMPLES", tmp_path)
    assert check.problems() == [f"there are no examples in {tmp_path.name}"]
    assert check.documents() == []


def test_a_missing_directory_is_caught(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(check, "EXAMPLES", tmp_path / "nowhere")
    assert check.documents() == []


def test_a_document_that_does_not_import_is_caught(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    found = planted(monkeypatch, tmp_path, {"number": "18-SH-0473"})
    assert any("does not import" in problem for problem in found)


def test_too_few_girders_is_caught(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    document = shipped()
    document["girders"] = document["girders"][:2]
    for index, girder in enumerate(document["girders"]):
        girder["girder_index"] = index
    found = planted(monkeypatch, tmp_path, document)
    assert any("the distribution equations want" in problem for problem in found)


def test_too_few_details_is_caught(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    document = shipped()
    for index, girder in enumerate(document["girders"]):
        girder["details"] = girder["details"][:1] if index == 0 else []
    found = planted(monkeypatch, tmp_path, document)
    assert any("the coverage line" in problem for problem in found)


def test_one_detail_category_is_caught(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    document = shipped()
    for girder in document["girders"]:
        for detail in girder["details"]:
            detail["category_name"] = "E"
            detail["kind"] = "cover_plate_end"
    found = planted(monkeypatch, tmp_path, document)
    assert any("one branch of the category table" in problem for problem in found)


def test_no_worst_category_detail_is_caught(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    document = shipped()
    for girder in document["girders"]:
        for detail in girder["details"]:
            if detail["category_name"] == check.WORST_CATEGORY:
                detail["category_name"] = "C"
                detail["kind"] = "stiffener_weld"
    found = planted(monkeypatch, tmp_path, document)
    assert any("never reaches the branch" in problem for problem in found)


def test_the_summary_names_what_is_in_each_example() -> None:
    lines = check.summary()
    assert len(lines) == len(check.documents())
    assert "girders" in lines[0]
    assert "categories" in lines[0]


def test_the_summary_prints_on_request(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main(["--list"]) == 0
    assert "check_examples: salt-fork-creek.json" in capsys.readouterr().out


def test_a_problem_is_reported_and_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(check, "problems", lambda: ["the example is missing something"])
    assert check.main([]) == 1
    out = capsys.readouterr().out
    assert "check_examples: the example is missing something" in out
    assert "1 problem(s)" in out
