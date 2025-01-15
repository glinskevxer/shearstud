"""Unit discipline.

Every number that crosses a public boundary in this package carries its unit in
its own name. There is no quantity type and no dimensional analysis at runtime;
there is a naming rule, and ``shearstud.tools.check_units`` enforces it against
the source. That trade is deliberate. A wrapper type would be checked once at
the boundary and then unwrapped, while a suffix is visible at every call site
and in every traceback.

The system is US customary throughout, because the load rating and fatigue
provisions this package implements are published that way and converting twice
to work in a different system only adds a place to be wrong.
"""

from __future__ import annotations

from typing import Final

from shearstud.errors import UnitError

#: Suffix to human name. ``check_units`` reads this dict, so adding a unit means
#: adding it here and nowhere else.
SUFFIXES: Final[dict[str, str]] = {
    "in": "inches",
    "ft": "feet",
    "mi": "miles",
    "in2": "square inches",
    "in3": "cubic inches, section modulus",
    "in4": "inches to the fourth, moment of inertia",
    "kip": "kips, thousands of pounds force",
    "klf": "kips per linear foot",
    "kipin": "kip inches",
    "kipft": "kip feet",
    "ksi": "kips per square inch",
    "ue": "microstrain, parts per million",
    "hz": "hertz",
    "s": "seconds",
    "deg": "degrees",
    "degf": "degrees fahrenheit",
    "yr": "years",
    "day": "days",
    "cyc": "cycles",
    "pct": "percent, 0 to 100",
    "frac": "fraction, 0 to 1",
}

#: Young's modulus for structural steel, the one constant used often enough that
#: passing it around would be noise.
STEEL_E_KSI: Final[float] = 29000.0

#: Coefficient of thermal expansion for structural steel, per degree Fahrenheit.
STEEL_ALPHA_PER_DEGF: Final[float] = 6.5e-6

_INCHES_PER_FOOT: Final[float] = 12.0
_FEET_PER_MILE: Final[float] = 5280.0


def ft_to_in(length_ft: float) -> float:
    """Feet to inches."""
    return length_ft * _INCHES_PER_FOOT


def in_to_ft(length_in: float) -> float:
    """Inches to feet."""
    return length_in / _INCHES_PER_FOOT


def mi_to_ft(distance_mi: float) -> float:
    """Miles to feet."""
    return distance_mi * _FEET_PER_MILE


def kipft_to_kipin(moment_kipft: float) -> float:
    """Kip feet to kip inches."""
    return moment_kipft * _INCHES_PER_FOOT


def kipin_to_kipft(moment_kipin: float) -> float:
    """Kip inches to kip feet."""
    return moment_kipin / _INCHES_PER_FOOT


def strain_to_stress_ksi(strain_ue: float, modulus_ksi: float = STEEL_E_KSI) -> float:
    """Convert microstrain to stress through Hooke's law.

    The microstrain convention is parts per million, so the division by 1e6 is
    part of the unit and not a fudge factor.
    """
    return strain_ue * 1e-6 * modulus_ksi


def stress_to_strain_ue(stress_ksi: float, modulus_ksi: float = STEEL_E_KSI) -> float:
    """Convert stress to microstrain through Hooke's law."""
    if modulus_ksi <= 0.0:
        raise UnitError("modulus must be positive")
    return stress_ksi / modulus_ksi * 1e6


def thermal_strain_ue(delta_degf: float, alpha_per_degf: float = STEEL_ALPHA_PER_DEGF) -> float:
    """Free thermal strain for a temperature change, in microstrain.

    Positive ``delta_degf`` means the steel got warmer, which a bonded gauge on
    an unrestrained member reads as tension it is not carrying.
    """
    return delta_degf * alpha_per_degf * 1e6


def unit_of(name: str) -> str:
    """Return the suffix on ``name``, or raise if it does not carry one.

    ``check_units`` uses this on parameter and field names, so the error message
    is what a developer sees when they add an unsuffixed float.
    """
    tail = name.rsplit("_", 1)[-1] if "_" in name else ""
    if tail not in SUFFIXES:
        raise UnitError(f"{name!r} carries no known unit suffix")
    return tail


def has_unit(name: str) -> bool:
    """True when ``name`` ends in a registered unit suffix."""
    tail = name.rsplit("_", 1)[-1] if "_" in name else ""
    return tail in SUFFIXES
