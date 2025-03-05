"""Structure number parsing, which is strict on purpose."""

from __future__ import annotations

import pytest

from shearstud.errors import InputError
from shearstud.structure.identity import StructureNumber, parse, try_parse

pytestmark = pytest.mark.store


def test_a_plain_number_round_trips() -> None:
    n = parse("18-SH-0473")
    assert n.county_code == 18
    assert n.route_class == "SH"
    assert n.sequence == 473
    assert n.parallel == ""
    assert str(n) == "18-SH-0473"


def test_a_parallel_suffix_is_kept() -> None:
    n = parse("18-SH-0473B")
    assert n.parallel == "B"
    assert n.is_parallel
    assert str(n) == "18-SH-0473B"


def test_a_structure_without_a_suffix_is_not_parallel() -> None:
    assert not parse("07-CR-1204").is_parallel


@pytest.mark.parametrize(
    "text",
    ["18-sh-0473", "  18-SH-0473  ", "18 SH 0473", "18-SH 0473", "18   SH   0473"],
)
def test_case_and_separators_are_forgiven(text: str) -> None:
    assert parse(text) == parse("18-SH-0473")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "18-SH",
        "18-SH-473",
        "18-SH-04731",
        "8-SH-0473",
        "18-S-0473",
        "18-SHH-0473",
        "18/SH/0473",
        "18-SH-0473BB",
        "18-SH-047A",
        "SH-18-0473",
    ],
)
def test_a_malformed_number_is_refused(text: str) -> None:
    with pytest.raises(InputError):
        parse(text)


def test_the_error_shows_what_was_handed_in() -> None:
    with pytest.raises(InputError, match="not a structure number"):
        parse("bridge 12")


def test_an_unknown_route_class_is_refused() -> None:
    with pytest.raises(InputError, match="unknown route class"):
        parse("18-ZZ-0473")


@pytest.mark.parametrize("county", [0, 65, 99])
def test_a_county_outside_the_range_is_refused(county: int) -> None:
    with pytest.raises(InputError, match="outside 1 to 64"):
        StructureNumber(county_code=county, route_class="SH", sequence=473)


def test_county_zero_is_refused_through_the_parser_too() -> None:
    with pytest.raises(InputError, match="outside 1 to 64"):
        parse("00-SH-0473")


def test_a_lower_case_suffix_built_directly_is_refused() -> None:
    with pytest.raises(InputError, match="upper case"):
        StructureNumber(county_code=18, route_class="SH", sequence=473, parallel="b")


def test_a_multi_letter_suffix_built_directly_is_refused() -> None:
    with pytest.raises(InputError, match="single letter"):
        StructureNumber(county_code=18, route_class="SH", sequence=473, parallel="AB")


def test_a_sequence_that_does_not_fit_is_refused() -> None:
    with pytest.raises(InputError, match="four digits"):
        StructureNumber(county_code=18, route_class="SH", sequence=10000)


def test_the_sibling_shares_everything_but_the_suffix() -> None:
    a = parse("18-SH-0473A")
    b = a.sibling("B")
    assert str(b) == "18-SH-0473B"
    assert b.without_parallel() == a.without_parallel()


def test_a_sibling_needs_a_suffix() -> None:
    with pytest.raises(InputError, match="needs a parallel suffix"):
        parse("18-SH-0473A").sibling("")


def test_the_sibling_lower_cases_are_lifted() -> None:
    assert parse("18-SH-0473A").sibling("c").parallel == "C"


def test_dropping_the_suffix_gives_the_crossing() -> None:
    assert str(parse("18-SH-0473B").without_parallel()) == "18-SH-0473"


def test_numbers_sort_the_way_the_file_cabinet_does() -> None:
    numbers = [
        parse("18-SH-0473B"),
        parse("07-CR-1204"),
        parse("18-IH-0012"),
        parse("18-SH-0473A"),
        parse("18-SH-0100"),
    ]
    assert [str(n) for n in sorted(numbers)] == [
        "07-CR-1204",
        "18-IH-0012",
        "18-SH-0100",
        "18-SH-0473A",
        "18-SH-0473B",
    ]


def test_two_numbers_with_the_same_text_are_equal_and_hash_alike() -> None:
    assert parse("18-SH-0473") == parse("18 sh 0473")
    assert len({parse("18-SH-0473"), parse("18-SH-0473")}) == 1


def test_try_parse_returns_none_instead_of_raising() -> None:
    assert try_parse("") is None
    assert try_parse("Structure Number") is None


def test_try_parse_returns_the_number_when_there_is_one() -> None:
    n = try_parse("18-SH-0473")
    assert n is not None
    assert n.sequence == 473


def test_a_zero_sequence_is_allowed_because_the_file_has_one() -> None:
    assert str(parse("02-FM-0000")) == "02-FM-0000"
