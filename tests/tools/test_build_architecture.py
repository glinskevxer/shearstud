"""The architecture page, generated from the table the check enforces."""

from __future__ import annotations

import pytest

from shearstud.tools import build_architecture as build
from shearstud.tools.check_layers import ALLOWED

pytestmark = pytest.mark.tools


def test_the_shipped_document_is_current() -> None:
    assert build.DOCUMENT.is_current(build.body())


def test_the_check_exits_zero_when_the_document_is_current() -> None:
    assert build.main(["--check"]) == 0


def test_every_layer_in_the_table_is_described() -> None:
    for layer in ALLOWED:
        assert layer in build.LAYER_PURPOSE, layer


def test_every_described_layer_is_in_the_table() -> None:
    for layer in build.LAYER_PURPOSE:
        assert layer in ALLOWED, layer


def test_the_layer_order_covers_the_table() -> None:
    assert set(build.LAYER_ORDER) == set(ALLOWED)


def test_the_order_runs_bottom_up() -> None:
    # Anything a layer may import has to appear before it in the order.
    positions = {layer: index for index, layer in enumerate(build.LAYER_ORDER)}
    for layer, allowed in ALLOWED.items():
        for other in allowed:
            assert positions[other] < positions[layer], f"{other} after {layer}"


def test_every_layer_row_carries_a_module_count() -> None:
    for row in build.layer_rows():
        assert int(row[1]) > 0


def test_every_layer_row_carries_a_line_count() -> None:
    for row in build.layer_rows():
        assert int(row[2]) > 0


def test_the_line_counts_add_up_to_the_package() -> None:
    from shearstud.tools.walk import source_files

    total = sum(len(source.lines()) for source in source_files(include_tools=True))
    assert sum(int(row[2]) for row in build.layer_rows()) == total


def test_the_import_rows_match_the_table() -> None:
    rows = {row[0]: row[1] for row in build.import_rows()}
    assert rows["geometry"] == "nothing above the foundation"
    assert "geometry" in rows["loads"]


def test_the_module_rows_leave_out_the_package_inits() -> None:
    for row in build.module_rows("geometry"):
        assert "__init__" not in row[0]


def test_every_module_row_carries_its_first_docstring_line() -> None:
    for row in build.module_rows("geometry"):
        assert row[2].strip()


def test_the_geometry_modules_are_listed() -> None:
    names = {row[0] for row in build.module_rows("geometry")}
    assert "`shearstud.geometry.section`" in names
    assert "`shearstud.geometry.plate`" in names


def test_the_top_level_modules_are_listed() -> None:
    names = {row[0] for row in build.module_rows("")}
    assert "`shearstud.units`" in names
    assert "`shearstud.errors`" in names


def test_the_document_names_the_foundation() -> None:
    text = build.body()
    assert "`shearstud.units`" in text
    assert "`shearstud.errors`" in text


def test_the_document_counts_the_sql_statements() -> None:
    from shearstud.tools.check_sql import statement_count

    assert f"holds {statement_count()} SQL statements" in build.body()


def test_the_document_names_the_command_that_wrote_it() -> None:
    assert "build_architecture" in build.DOCUMENT.wrap(build.body())


def test_a_layer_with_no_modules_is_left_out() -> None:
    listed = {row[0] for row in build.layer_rows()}
    assert "" not in listed
