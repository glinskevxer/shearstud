"""Every exception the package raises on purpose.

One base class so a caller can catch the whole package with a single ``except``
and still tell an input problem apart from a state problem. Nothing here wraps
a builtin: a ``KeyError`` escaping this package is a bug in this package, not a
condition a caller is meant to handle.
"""

from __future__ import annotations


class ShearstudError(Exception):
    """Base for every error raised on purpose by this package."""


class InputError(ShearstudError):
    """A value handed in by a caller is outside the range the model accepts.

    Raised before any work happens. Nothing has been written and no partial
    result exists when this is raised.
    """


class GeometryError(InputError):
    """A cross section cannot be built from the plates it was given."""


class UnitError(InputError):
    """A quantity was supplied in units the receiving function does not take."""


class RecordError(InputError):
    """A measurement record is malformed, out of order, or internally
    inconsistent."""


class StateError(ShearstudError):
    """The object is not in a state where the requested operation makes sense.

    The distinction from :class:`InputError` matters to a caller: retrying with
    a different argument may fix an input error, and will not fix this one.
    """


class NotRatedError(StateError):
    """A rating summary was asked for before any rating had been computed."""


class StorageError(ShearstudError):
    """The book of record could not answer, or would be left inconsistent."""


class MigrationError(StorageError):
    """The stored schema version does not line up with the code's own."""


class ConfigError(ShearstudError):
    """A policy file, factor table, or catalogue could not be loaded."""
