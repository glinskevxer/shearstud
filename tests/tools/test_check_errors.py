"""The error discipline check, and the fallback handler it lets through."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from shearstud.tools import check_errors as check
from shearstud.tools.walk import SourceFile

pytestmark = pytest.mark.tools

Plant = Callable[..., None]
Source = Callable[[str, str], SourceFile]

HEAD = '"""A module that says something useful about itself."""'


def planted_code(source: Source, planted: Plant, body: str) -> list[str]:
    planted(check, [source("geometry/x.py", f"{HEAD}\n\n\n{body}\n")])
    return check.problems()


def test_the_real_tree_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_tree() -> None:
    assert check.main() == 0


def test_the_package_errors_are_the_ones_it_declares() -> None:
    names = check.error_names()
    assert "ShearstudError" in names
    assert "InputError" in names
    assert "StorageError" in names


def test_a_foreign_error_is_caught(source: Source, planted: Plant) -> None:
    found = planted_code(source, planted, 'def f() -> None:\n    raise ValueError("no")')
    assert any("raises ValueError, which is not ours" in p for p in found)


def test_a_package_error_is_accepted(source: Source, planted: Plant) -> None:
    found = planted_code(source, planted, 'def f() -> None:\n    raise InputError("no")')
    assert found == []


def test_not_implemented_is_allowed(source: Source, planted: Plant) -> None:
    found = planted_code(source, planted, "def f() -> None:\n    raise NotImplementedError")
    assert found == []


def test_an_error_with_no_message_is_caught(source: Source, planted: Plant) -> None:
    found = planted_code(source, planted, "def f() -> None:\n    raise InputError()")
    assert any("with no message" in p for p in found)


def test_a_bare_reraise_is_not_a_problem(source: Source, planted: Plant) -> None:
    body = "def f() -> None:\n    try:\n        pass\n    except InputError:\n        raise"
    found = planted_code(source, planted, body)
    assert found == []


def test_catching_everything_bare_is_caught(source: Source, planted: Plant) -> None:
    body = "def f() -> None:\n    try:\n        pass\n    except:\n        pass"
    found = planted_code(source, planted, body)
    assert any("catches everything bare" in p for p in found)


def test_catching_exception_without_reraising_is_caught(source: Source, planted: Plant) -> None:
    body = (
        "def f() -> None:\n    try:\n        pass\n    except Exception:\n"
        "        print('never mind')"
    )
    found = planted_code(source, planted, body)
    assert any("without re raising" in p for p in found)


def test_catching_exception_and_reraising_is_accepted(source: Source, planted: Plant) -> None:
    body = (
        "def f() -> None:\n    try:\n        pass\n    except Exception:\n"
        "        print('rolling back')\n        raise"
    )
    found = planted_code(source, planted, body)
    assert found == []


def test_chaining_with_from_counts_as_using_the_error(source: Source, planted: Plant) -> None:
    body = (
        "def f() -> None:\n    try:\n        pass\n    except KeyError as exc:\n"
        '        raise InputError("no") from exc'
    )
    found = planted_code(source, planted, body)
    assert found == []


def test_naming_the_error_in_the_message_counts_as_using_it(source: Source, planted: Plant) -> None:
    body = (
        "def f() -> None:\n    try:\n        pass\n    except KeyError as exc:\n"
        '        raise InputError(f"no: {exc}") from exc'
    )
    found = planted_code(source, planted, body)
    assert found == []


def test_a_short_fallback_is_accepted(source: Source, planted: Plant) -> None:
    body = "def f() -> None:\n    try:\n        pass\n    except InputError:\n        return None"
    found = planted_code(source, planted, body)
    assert found == []


def test_a_long_handler_that_ignores_the_error_is_caught(source: Source, planted: Plant) -> None:
    body = (
        "def f() -> None:\n    try:\n        pass\n    except InputError:\n"
        "        print(1)\n        print(2)\n        print(3)\n        print(4)"
    )
    found = planted_code(source, planted, body)
    assert any("does not use it" in p for p in found)


def test_a_fallback_that_hides_a_raise_is_not_a_fallback(source: Source, planted: Plant) -> None:
    body = (
        "def f() -> None:\n    try:\n        pass\n    except InputError:\n"
        '        raise StorageError("different")'
    )
    found = planted_code(source, planted, body)
    assert found == []


def test_the_fallback_limit_is_a_small_number() -> None:
    assert 1 <= check.MAX_FALLBACK_STATEMENTS <= 5


def test_the_allowed_foreign_errors_are_not_package_errors() -> None:
    assert check.ALLOWED_FOREIGN & set(check.error_names()) == set()


def test_the_check_exits_one_when_something_is_wrong(source: Source, planted: Plant) -> None:
    planted(
        check,
        [source("geometry/x.py", f'{HEAD}\n\n\ndef f() -> None:\n    raise ValueError("no")\n')],
    )
    assert check.main() == 1
