"""The check that says which modules anybody thought about."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from shearstud.tools import check_tests as check
from shearstud.tools.walk import SourceFile

pytestmark = pytest.mark.tools

Plant = Callable[..., None]
Source = Callable[[str, str], SourceFile]
Suite = Callable[[str, str], SourceFile]

HEAD = '"""A module that says something useful about itself."""'
MARKED = "import pytest\n\npytestmark = pytest.mark.tools"


def test_the_real_tree_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_tree() -> None:
    assert check.main() == 0


def test_every_module_is_named_in_the_expected_list() -> None:
    names = check.module_names()
    assert "shearstud.geometry.section" in names
    assert "shearstud.rating.rate" in names


def test_a_package_init_is_exempt() -> None:
    assert "shearstud.geometry" not in check.module_names()


def test_a_module_with_no_test_file_is_caught(source: Source, suite: Suite, planted: Plant) -> None:
    planted(check, [source("geometry/newthing.py", f"{HEAD}\n")])
    planted(
        check,
        [suite("test_section.py", f"{MARKED}\n\n\ndef test_x() -> None:\n    assert True\n")],
        "suite_files",
    )
    found = check.problems()
    assert any("has no test_newthing.py" in p for p in found)


def test_a_module_with_a_test_file_is_accepted(
    source: Source, suite: Suite, planted: Plant
) -> None:
    planted(check, [source("geometry/newthing.py", f"{HEAD}\n")])
    planted(
        check,
        [suite("test_newthing.py", f"{MARKED}\n\n\ndef test_x() -> None:\n    assert True\n")],
        "suite_files",
    )
    assert check.problems() == []


def test_a_test_file_with_no_marker_is_caught(source: Source, suite: Suite, planted: Plant) -> None:
    planted(check, [source("geometry/newthing.py", f"{HEAD}\n")])
    planted(
        check,
        [suite("test_newthing.py", "def test_x() -> None:\n    assert True\n")],
        "suite_files",
    )
    assert any("sets no pytestmark" in p for p in check.problems())


def test_a_test_file_with_no_tests_is_caught(source: Source, suite: Suite, planted: Plant) -> None:
    planted(check, [source("geometry/newthing.py", f"{HEAD}\n")])
    planted(check, [suite("test_newthing.py", f"{MARKED}\n")], "suite_files")
    assert any("holds no tests" in p for p in check.problems())


def test_a_test_that_asserts_nothing_is_caught(
    source: Source, suite: Suite, planted: Plant
) -> None:
    planted(check, [source("geometry/newthing.py", f"{HEAD}\n")])
    planted(
        check,
        [
            suite(
                "test_newthing.py",
                f"{MARKED}\n\n\ndef test_x() -> None:\n    value = 1 + 1\n    print(value)\n",
            )
        ],
        "suite_files",
    )
    assert any("asserts nothing" in p for p in check.problems())


def test_a_test_that_expects_a_raise_counts_as_asserting(
    source: Source, suite: Suite, planted: Plant
) -> None:
    planted(check, [source("geometry/newthing.py", f"{HEAD}\n")])
    planted(
        check,
        [
            suite(
                "test_newthing.py",
                f"{MARKED}\n\n\ndef test_x() -> None:\n"
                "    with pytest.raises(ValueError):\n        raise ValueError\n",
            )
        ],
        "suite_files",
    )
    assert check.problems() == []


def test_the_aliases_all_name_a_real_module() -> None:
    names = set(check.module_names())
    for module in check.ALIASES:
        assert module in names, module


def test_the_exemptions_are_all_package_inits() -> None:
    for module in check.EXEMPT_MODULES:
        assert module.count(".") <= 2, module


def test_the_expected_name_follows_the_module() -> None:
    assert check._expected_name("shearstud.geometry.section") == "test_section.py"


def test_the_expected_name_honours_an_alias() -> None:
    assert check._expected_name("shearstud.cli.main") == "test_cli_main.py"


def test_the_check_exits_one_when_something_is_wrong(
    source: Source, suite: Suite, planted: Plant
) -> None:
    planted(check, [source("geometry/newthing.py", f"{HEAD}\n")])
    planted(
        check,
        [suite("test_section.py", f"{MARKED}\n\n\ndef test_x() -> None:\n    assert True\n")],
        "suite_files",
    )
    assert check.main() == 1
