"""The error tree is part of the contract, so its shape is asserted.

A caller writes ``except InputError`` to mean "I gave it something wrong" and
``except StateError`` to mean "the retry will not help". Those two have to stay
disjoint, and every error in the package has to sit under one root.
"""

from __future__ import annotations

import inspect

import pytest

from shearstud import errors

pytestmark = pytest.mark.tools

ALL_ERRORS = [
    obj
    for _, obj in inspect.getmembers(errors, inspect.isclass)
    if issubclass(obj, BaseException) and obj.__module__ == errors.__name__
]


def test_the_module_declares_the_errors_this_suite_expects() -> None:
    names = {cls.__name__ for cls in ALL_ERRORS}
    assert {
        "ShearstudError",
        "InputError",
        "GeometryError",
        "UnitError",
        "RecordError",
        "StateError",
        "NotRatedError",
        "StorageError",
        "MigrationError",
        "ConfigError",
    } <= names


def test_every_error_descends_from_the_package_root() -> None:
    for cls in ALL_ERRORS:
        assert issubclass(cls, errors.ShearstudError), cls.__name__


def test_the_root_is_an_exception_and_not_a_base_exception_shortcut() -> None:
    assert issubclass(errors.ShearstudError, Exception)
    assert not issubclass(errors.ShearstudError, KeyboardInterrupt)


def test_input_and_state_do_not_overlap() -> None:
    assert not issubclass(errors.InputError, errors.StateError)
    assert not issubclass(errors.StateError, errors.InputError)


def test_the_input_family_is_catchable_as_one() -> None:
    for cls in (errors.GeometryError, errors.UnitError, errors.RecordError):
        assert issubclass(cls, errors.InputError)


def test_the_storage_family_is_catchable_as_one() -> None:
    assert issubclass(errors.MigrationError, errors.StorageError)


def test_not_rated_is_a_state_problem_not_an_input_problem() -> None:
    assert issubclass(errors.NotRatedError, errors.StateError)
    assert not issubclass(errors.NotRatedError, errors.InputError)


def test_config_hangs_off_the_root_directly() -> None:
    assert issubclass(errors.ConfigError, errors.ShearstudError)
    assert not issubclass(errors.ConfigError, errors.InputError)


def test_every_error_carries_a_docstring() -> None:
    for cls in ALL_ERRORS:
        assert (cls.__doc__ or "").strip(), cls.__name__


def test_an_error_keeps_the_message_it_was_given() -> None:
    err = errors.GeometryError("web thickness must be positive")
    assert str(err) == "web thickness must be positive"
    assert isinstance(err, errors.ShearstudError)
