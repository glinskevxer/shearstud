"""The unit suffix check, and the three families it lets through."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from shearstud.tools import check_units as check
from shearstud.tools.walk import SourceFile

pytestmark = pytest.mark.tools

Plant = Callable[..., None]
Source = Callable[[str, str], SourceFile]

MODULE_HEAD = '"""A module that says something useful about itself."""'


def test_the_real_tree_is_clean() -> None:
    assert check.problems() == []


def test_the_check_exits_zero_on_a_clean_tree() -> None:
    assert check.main() == 0


def test_a_float_parameter_with_no_suffix_is_caught(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                f'''
                {MODULE_HEAD}


                def widen(width: float) -> float:
                    """Make it wider by an inch."""
                    return width + 1.0
                ''',
            )
        ],
    )
    found = check.problems()
    assert any("takes a float 'width'" in p for p in found)


def test_a_float_parameter_with_a_suffix_is_accepted(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                f'''
                {MODULE_HEAD}


                def widen(width_in: float) -> float:
                    """Make it wider by an inch."""
                    return width_in + 1.0
                ''',
            )
        ],
    )
    assert check.problems() == []


def test_a_field_with_no_suffix_is_caught(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                f'''
                {MODULE_HEAD}


                class Girder:
                    """A girder line through one structural unit."""

                    depth: float
                ''',
            )
        ],
    )
    assert any("float field 'depth'" in p for p in check.problems())


def test_a_field_with_a_suffix_is_accepted(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                f'''
                {MODULE_HEAD}


                class Girder:
                    """A girder line through one structural unit."""

                    depth_in: float
                ''',
            )
        ],
    )
    assert check.problems() == []


def test_an_integer_is_not_checked(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                f'''
                {MODULE_HEAD}


                def repeat(times: int) -> int:
                    """How many passes to make over the record."""
                    return times
                ''',
            )
        ],
    )
    assert check.problems() == []


def test_a_private_function_is_left_alone(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                f"""
                {MODULE_HEAD}


                def _widen(width: float) -> float:
                    return width
                """,
            )
        ],
    )
    assert check.problems() == []


def test_self_is_left_alone(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                f'''
                {MODULE_HEAD}


                class Girder:
                    """A girder line through one structural unit."""

                    def widen(self, width_in: float) -> float:
                        """Make it wider."""
                        return width_in
                ''',
            )
        ],
    )
    assert check.problems() == []


@pytest.mark.parametrize("name", sorted(check.DIMENSIONLESS)[:6])
def test_a_dimensionless_name_is_let_through(source: Source, planted: Plant, name: str) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                f'''
                {MODULE_HEAD}


                def take({name}: float) -> float:
                    """Use the value the caller handed in."""
                    return {name}
                ''',
            )
        ],
    )
    assert check.problems() == []


@pytest.mark.parametrize("name", ["distributed", "factored_dead", "live_effect"])
def test_a_load_effect_is_let_through(source: Source, planted: Plant, name: str) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                f'''
                {MODULE_HEAD}


                def take({name}: float) -> float:
                    """Use the load effect the caller handed in."""
                    return {name}
                ''',
            )
        ],
    )
    assert check.problems() == []


@pytest.mark.parametrize("name", ["days", "years_remaining", "annual_cycles"])
def test_a_duration_or_count_is_let_through(source: Source, planted: Plant, name: str) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                f'''
                {MODULE_HEAD}


                def take({name}: float) -> float:
                    """Use the duration the caller handed in."""
                    return {name}
                ''',
            )
        ],
    )
    assert check.problems() == []


def test_the_exemption_families_do_not_overlap() -> None:
    families = [
        check.DIMENSIONLESS,
        check.LOAD_EFFECTS,
        check.DURATIONS_AND_COUNTS,
        check.CONVENTIONAL,
    ]
    for index, first in enumerate(families):
        for second in families[index + 1 :]:
            assert first & second == set(), f"{first & second} is in two families"


def test_every_exemption_is_in_the_combined_set() -> None:
    combined = (
        check.DIMENSIONLESS | check.LOAD_EFFECTS | check.DURATIONS_AND_COUNTS | check.CONVENTIONAL
    )
    assert combined == check.EXEMPT


def test_no_exemption_already_carries_a_unit_suffix() -> None:
    from shearstud.units import has_unit

    # A name that already has a suffix does not need an exemption, and one that
    # has both is an exemption nobody will notice going stale.
    wrong = sorted(name for name in check.EXEMPT if has_unit(name))
    assert wrong == []


def test_the_check_exits_one_when_something_is_wrong(source: Source, planted: Plant) -> None:
    planted(
        check,
        [
            source(
                "x.py",
                f'''
                {MODULE_HEAD}


                def widen(width: float) -> float:
                    """Make it wider by an inch."""
                    return width + 1.0
                ''',
            )
        ],
    )
    assert check.main() == 1
