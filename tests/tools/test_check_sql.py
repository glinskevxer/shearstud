"""The SQL check, and the opt out each module declares for itself."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from shearstud.tools import check_sql as check
from shearstud.tools.walk import SourceFile

pytestmark = pytest.mark.tools

Plant = Callable[..., None]
Source = Callable[[str, str], SourceFile]

HEAD = '"""A module that says something useful about itself."""'


def planted_code(source: Source, planted: Plant, where: str, body: str) -> list[str]:
    planted(check, [source(where, f"{HEAD}\n\n{body}\n")])
    return check.problems()


def test_the_real_tree_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_tree() -> None:
    assert check.main() == 0


def test_the_package_holds_a_plausible_number_of_statements() -> None:
    assert 30 < check.statement_count() < 200


def test_sql_outside_the_store_is_caught(source: Source, planted: Plant) -> None:
    found = planted_code(source, planted, "rating/x.py", 'QUERY = "SELECT number FROM structures"')
    assert any("outside the store layer" in p for p in found)


def test_sql_inside_the_store_is_accepted(source: Source, planted: Plant) -> None:
    found = planted_code(source, planted, "store/x.py", 'QUERY = "SELECT number FROM structures"')
    assert found == []


def test_the_tools_layer_is_not_looked_at(source: Source, planted: Plant) -> None:
    found = planted_code(source, planted, "tools/x.py", 'PATTERN = "SELECT * FROM anything"')
    assert found == []


def test_a_star_select_is_caught(source: Source, planted: Plant) -> None:
    found = planted_code(source, planted, "store/x.py", 'QUERY = "SELECT * FROM structures"')
    assert any("SELECT *" in p for p in found)


def test_a_star_select_is_caught_in_an_f_string(source: Source, planted: Plant) -> None:
    body = 'TABLE = "structures"\n\n\ndef read() -> str:\n    return f"SELECT * FROM {TABLE}"'
    found = planted_code(source, planted, "store/x.py", body)
    assert any("SELECT *" in p for p in found)


def test_interpolating_a_value_is_caught(source: Source, planted: Plant) -> None:
    body = (
        "def read(number: str) -> str:\n"
        '    return f"SELECT name FROM structures WHERE number = {number}"'
    )
    found = planted_code(source, planted, "store/x.py", body)
    assert any("interpolates 'number'" in p for p in found)


def test_interpolating_a_module_constant_is_accepted(source: Source, planted: Plant) -> None:
    body = (
        'COLUMNS = "number, name"\n\n\n'
        "def read() -> str:\n"
        '    return f"SELECT {COLUMNS} FROM structures"'
    )
    found = planted_code(source, planted, "store/x.py", body)
    assert found == []


def test_a_declared_opt_out_is_honoured(source: Source, planted: Plant) -> None:
    body = (
        'SQL_NAME_INTERPOLATION = ("count_rows",)\n\n\n'
        "def count_rows(table: str) -> str:\n"
        '    return f"SELECT COUNT(*) FROM {table}"'
    )
    found = planted_code(source, planted, "store/x.py", body)
    assert found == []


def test_an_opt_out_only_covers_the_function_it_names(source: Source, planted: Plant) -> None:
    body = (
        'SQL_NAME_INTERPOLATION = ("count_rows",)\n\n\n'
        "def count_rows(table: str) -> str:\n"
        '    return f"SELECT COUNT(*) FROM {table}"\n\n\n'
        "def read_rows(table: str) -> str:\n"
        '    return f"SELECT name FROM {table}"'
    )
    found = planted_code(source, planted, "store/x.py", body)
    assert any("interpolates 'table'" in p for p in found)
    assert len(found) == 1


def test_a_module_with_no_opt_out_declares_none(source: Source) -> None:
    file = source("store/x.py", f"{HEAD}\n")
    assert check._declared_opt_outs(file) == set()


def test_the_store_module_declares_its_own_opt_out() -> None:
    from shearstud.store import db

    assert db.SQL_NAME_INTERPOLATION == ("row_count",)


def test_the_declared_opt_out_names_a_real_function() -> None:
    from shearstud.store import db

    for name in db.SQL_NAME_INTERPOLATION:
        assert callable(getattr(db, name))


def test_a_plain_string_that_is_not_sql_is_ignored(source: Source, planted: Plant) -> None:
    found = planted_code(source, planted, "rating/x.py", 'MESSAGE = "choose a vehicle"')
    assert found == []


def test_the_check_exits_one_when_something_is_wrong(source: Source, planted: Plant) -> None:
    planted(check, [source("rating/x.py", f'{HEAD}\n\nQUERY = "SELECT number FROM structures"\n')])
    assert check.main() == 1
