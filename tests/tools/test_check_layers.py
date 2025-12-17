"""The layering check, and the two siblings that may not talk to each other."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from shearstud.tools import check_layers as check
from shearstud.tools.walk import SourceFile

pytestmark = pytest.mark.tools

Plant = Callable[..., None]
Source = Callable[[str, str], SourceFile]

HEAD = '"""A module that says something useful about itself."""'


def planted_import(source: Source, planted: Plant, where: str, statement: str) -> list[str]:
    planted(check, [source(where, f"{HEAD}\n\n{statement}\n")])
    return check.problems()


def test_the_real_tree_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_tree() -> None:
    assert check.main() == 0


def test_the_only_orphan_layers_are_the_top_ones() -> None:
    assert check.orphans() == ["cli", "tools"]


def test_geometry_reaching_into_store_is_caught(source: Source, planted: Plant) -> None:
    found = planted_import(
        source, planted, "geometry/x.py", "from shearstud.store.db import connect"
    )
    assert found
    assert "geometry/x.py (geometry) imports shearstud.store.db (store)" in found[0]


def test_rating_reaching_into_cli_is_caught(source: Source, planted: Plant) -> None:
    found = planted_import(source, planted, "rating/x.py", "from shearstud.cli.main import main")
    assert any("(rating) imports shearstud.cli.main (cli)" in p for p in found)


def test_loads_reaching_into_signals_is_caught(source: Source, planted: Plant) -> None:
    found = planted_import(
        source, planted, "loads/x.py", "from shearstud.signals.series import StrainRecord"
    )
    assert any("(loads) imports shearstud.signals.series (signals)" in p for p in found)


def test_signals_reaching_into_loads_is_caught(source: Source, planted: Plant) -> None:
    found = planted_import(
        source, planted, "signals/x.py", "from shearstud.loads.axles import AxleTrain"
    )
    assert any("(signals) imports shearstud.loads.axles (loads)" in p for p in found)


def test_a_layer_may_import_from_below(source: Source, planted: Plant) -> None:
    found = planted_import(
        source, planted, "rating/x.py", "from shearstud.geometry.section import Section"
    )
    assert found == []


def test_every_layer_may_import_the_foundation(source: Source, planted: Plant) -> None:
    for layer in ("geometry", "loads", "signals", "rating", "store"):
        found = planted_import(
            source, planted, f"{layer}/x.py", "from shearstud.units import ft_to_in"
        )
        assert found == [], layer


def test_every_layer_may_import_the_errors(source: Source, planted: Plant) -> None:
    found = planted_import(
        source, planted, "geometry/x.py", "from shearstud.errors import InputError"
    )
    assert found == []


def test_a_module_may_import_its_own_layer(source: Source, planted: Plant) -> None:
    found = planted_import(
        source, planted, "geometry/x.py", "from shearstud.geometry.plate import Plate"
    )
    assert found == []


def test_a_top_level_module_may_import_nothing_but_the_foundation(
    source: Source, planted: Plant
) -> None:
    found = planted_import(
        source, planted, "x.py", "from shearstud.geometry.section import Section"
    )
    assert any("imports shearstud.geometry.section (geometry)" in p for p in found)


def test_a_layer_the_table_does_not_know_is_caught(source: Source, planted: Plant) -> None:
    found = planted_import(source, planted, "reporting/x.py", "x = 1")
    assert any("the table does not list" in p for p in found)


def test_the_standard_library_is_never_a_problem(source: Source, planted: Plant) -> None:
    found = planted_import(source, planted, "geometry/x.py", "import math\nimport sqlite3")
    assert found == []


def test_the_table_lists_every_layer_in_the_package() -> None:
    from shearstud.tools.walk import source_files

    layers = {source.layer for source in source_files(include_tools=True)}
    assert layers <= set(check.ALLOWED)


def test_no_layer_is_allowed_to_import_itself() -> None:
    for layer, allowed in check.ALLOWED.items():
        assert layer not in allowed


def test_the_allowances_are_transitive_downwards() -> None:
    # If rating may import store, it may import everything store may import.
    for layer, allowed in check.ALLOWED.items():
        for other in allowed:
            assert check.ALLOWED[other] <= allowed, f"{layer} skips a layer under {other}"


def test_the_check_exits_one_when_something_is_wrong(source: Source, planted: Plant) -> None:
    planted(check, [source("geometry/x.py", f"{HEAD}\n\nfrom shearstud.store.db import connect\n")])
    assert check.main() == 1
