"""Shear connectors: what holds the deck to the girder, and how far apart.

Composite action is an assumption every other module in this package makes. The
studs are what make it true, and they are checked twice for two different
reasons:

* **fatigue** decides the spacing. The shear flow at the interface reverses with
  every truck, and the studs have their own S-N curve, shallower than the plate
  details. A composite girder whose studs are too far apart loses composite
  action gradually, and nothing on the outside of the deck shows it;
* **strength** decides the total number between the point of maximum moment and
  the point of zero moment. That is a global count, not a spacing, and it is why
  the two checks cannot be combined into one.

The shear flow uses the section's own first moment about its neutral axis, which
is the same Q that appears in every shear stress calculation. Getting it from
the short term composite section rather than the steel section is the part worth
watching: the deck is part of what is being held on.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from shearstud.errors import InputError
from shearstud.geometry.composite import CompositeGirder, concrete_modulus_ksi
from shearstud.geometry.section import Section

#: Stud diameters this agency has on the shelf.
STANDARD_DIAMETERS_IN: Final[tuple[float, ...]] = (0.625, 0.75, 0.875, 1.0)

#: Minimum height to diameter ratio for a stud to count as a connector.
MIN_HEIGHT_RATIO: Final[float] = 4.0

#: Pitch limits, AASHTO LRFD 6.10.10.1.2, in stud diameters and in inches.
MIN_PITCH_DIAMETERS: Final[float] = 6.0
#: Furthest apart a row of studs may be, whatever the fatigue check allows.
#: Beyond this the deck lifts off the flange between the rows and the section
#: stops behaving as one, which is a failure the shear flow calculation has no
#: way of seeing.
MAX_PITCH_IN: Final[float] = 48.0

#: Fatigue I resistance coefficient, applied to the diameter squared. This is
#: the constant amplitude threshold, so it is the lowest of the three and a
#: finite life check will always allow more.
FATIGUE_I_COEFF: Final[float] = 5.5

#: Fatigue II coefficient is 34.5 minus 4.28 times the log of the cycle count,
#: with a floor of half the constant amplitude value.
FATIGUE_II_INTERCEPT: Final[float] = 34.5
FATIGUE_II_SLOPE: Final[float] = 4.28
FATIGUE_II_FLOOR_COEFF: Final[float] = 5.5 / 2.0


@dataclass(frozen=True, slots=True)
class StudSpec:
    """One shear stud, as a shop drawing gives it."""

    diameter_in: float
    height_in: float
    tensile_strength_ksi: float

    def __post_init__(self) -> None:
        if self.diameter_in <= 0.0:
            raise InputError(f"stud diameter {self.diameter_in} is not a diameter")
        if self.height_in < MIN_HEIGHT_RATIO * self.diameter_in:
            raise InputError(
                f"a {self.diameter_in} in stud needs to be at least "
                f"{MIN_HEIGHT_RATIO * self.diameter_in} in tall, not {self.height_in}"
            )
        if self.tensile_strength_ksi <= 0.0:
            raise InputError(f"stud strength {self.tensile_strength_ksi} is not a strength")

    @property
    def area_in2(self) -> float:
        """Cross sectional area of the shank."""
        return math.pi * self.diameter_in**2 / 4.0

    @property
    def is_standard(self) -> bool:
        """True when the diameter is one the agency stocks."""
        return any(abs(self.diameter_in - d) < 1.0e-9 for d in STANDARD_DIAMETERS_IN)

    def strength_kip(self, fc_ksi: float) -> float:
        """Nominal strength of one stud in a normal weight deck."""
        if fc_ksi <= 0.0:
            raise InputError(f"concrete strength {fc_ksi} is not a strength")
        concrete_bound = 0.5 * self.area_in2 * math.sqrt(fc_ksi * concrete_modulus_ksi(fc_ksi))
        steel_bound = self.area_in2 * self.tensile_strength_ksi
        return min(concrete_bound, steel_bound)

    def governed_by_steel(self, fc_ksi: float) -> bool:
        """True when the shank yields before the concrete crushes."""
        concrete_bound = 0.5 * self.area_in2 * math.sqrt(fc_ksi * concrete_modulus_ksi(fc_ksi))
        return self.area_in2 * self.tensile_strength_ksi <= concrete_bound

    def fatigue_resistance_kip(self, cycles: float | None = None) -> float:
        """Resistance of one stud to a repeated shear.

        ``cycles`` of ``None`` asks for the Fatigue I value, which is the
        constant amplitude threshold and does not depend on the count.
        """
        if cycles is None:
            return FATIGUE_I_COEFF * self.diameter_in**2
        if cycles <= 0.0:
            raise InputError(f"{cycles} cycles is not a life")
        alpha = FATIGUE_II_INTERCEPT - FATIGUE_II_SLOPE * math.log10(cycles)
        floor = FATIGUE_II_FLOOR_COEFF
        return max(alpha, floor) * self.diameter_in**2


def shear_flow_kip_per_in(section: Section, interface_y_in: float, shear_kip: float) -> float:
    """Horizontal shear per inch at a cut through the section.

    This is V times Q over I, with Q taken about the section's own neutral axis.
    A negative shear gives a negative flow, and the studs care about the range
    rather than the sign, so callers take the magnitude.
    """
    inertia_in4 = section.inertia_in4
    if inertia_in4 <= 0.0:
        raise InputError(f"{section.label}: inertia {inertia_in4} is not a stiffness")
    first_moment_in3 = section.first_moment_above_in3(interface_y_in)
    return shear_kip * first_moment_in3 / inertia_in4


def interface_flow_kip_per_in(girder: CompositeGirder, shear_kip: float) -> float:
    """Shear flow at the top of the steel, where the studs are.

    The short term composite section is used because live load is what the
    studs are being checked against, and live load is carried by the short term
    section.
    """
    section = girder.short_term
    return shear_flow_kip_per_in(section, girder.steel_top_in, shear_kip)


def required_pitch_in(
    girder: CompositeGirder,
    shear_range_kip: float,
    studs_per_row: int,
    stud: StudSpec,
    cycles: float | None = None,
) -> float:
    """Longest stud pitch that survives the fatigue shear range.

    A zero shear range means the studs are never worked and the pitch is decided
    by the spacing limits alone, so the maximum is returned rather than an
    infinity a caller would have to clamp.
    """
    if studs_per_row < 1:
        raise InputError(f"{studs_per_row} studs in a row is not a row")
    if shear_range_kip < 0.0:
        raise InputError(f"shear range {shear_range_kip} is negative")
    flow = abs(interface_flow_kip_per_in(girder, shear_range_kip))
    if flow <= 0.0:
        return MAX_PITCH_IN
    resistance_kip = studs_per_row * stud.fatigue_resistance_kip(cycles)
    return resistance_kip / flow


def pitch_limits_in(stud: StudSpec) -> tuple[float, float]:
    """Closest and furthest apart a row of studs may be."""
    return MIN_PITCH_DIAMETERS * stud.diameter_in, MAX_PITCH_IN


def usable_pitch_in(
    girder: CompositeGirder,
    shear_range_kip: float,
    studs_per_row: int,
    stud: StudSpec,
    cycles: float | None = None,
) -> float:
    """The required pitch clamped into the spacing limits.

    A required pitch below the minimum is not a spacing that can be built; it
    means more studs per row are needed, and the caller finds that out by the
    clamped answer coming back at the minimum.
    """
    required = required_pitch_in(girder, shear_range_kip, studs_per_row, stud, cycles)
    low_in, high_in = pitch_limits_in(stud)
    return min(max(required, low_in), high_in)


def rows_needed_for_strength(
    total_shear_kip: float, stud: StudSpec, fc_ksi: float, studs_per_row: int
) -> int:
    """Rows of studs between maximum moment and zero moment.

    Rounded up, because a fraction of a row is a row.
    """
    if studs_per_row < 1:
        raise InputError(f"{studs_per_row} studs in a row is not a row")
    if total_shear_kip < 0.0:
        raise InputError(f"total shear {total_shear_kip} is negative")
    per_row_kip = studs_per_row * stud.strength_kip(fc_ksi)
    return math.ceil(total_shear_kip / per_row_kip)
