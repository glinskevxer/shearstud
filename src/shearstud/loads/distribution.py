"""Live load distribution factors: how much of a lane one girder carries.

Two families of method live here and they do not mix cleanly, which is the thing
to understand before reading any of it.

The approximate equations are curve fits to grillage analyses, and the multiple
presence factor is already baked into them. The lever rule is a statics
calculation on a rigid deck, and it is not. So a lever rule answer has to be
multiplied by the multiple presence factor and an equation answer must not be,
and mixing those up is worth ten percent on a rating in whichever direction is
least convenient.

``apply_presence`` exists so the difference is written down at every call site
rather than remembered. The equations have a range of applicability and this
module refuses outside it rather than extrapolating, because the fits go
visibly wrong past their limits and a rating built on an extrapolated factor is
not a rating.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from shearstud.errors import InputError

#: Multiple presence factors, AASHTO LRFD Table 3.6.1.1.2-1, by lanes loaded.
PRESENCE_FACTORS: Final[dict[int, float]] = {1: 1.20, 2: 1.00, 3: 0.85}

#: Four or more lanes all take this one.
PRESENCE_FACTOR_MANY: Final[float] = 0.65

#: Range of applicability for the approximate equations, cross section type (a),
#: AASHTO LRFD Table 4.6.2.2.2b-1.
SPACING_RANGE_FT: Final[tuple[float, float]] = (3.5, 16.0)
SLAB_RANGE_IN: Final[tuple[float, float]] = (4.5, 12.0)
SPAN_RANGE_FT: Final[tuple[float, float]] = (20.0, 240.0)
STIFFNESS_RANGE_IN4: Final[tuple[float, float]] = (10_000.0, 7_000_000.0)
MIN_BEAMS: Final[int] = 4

#: How far from the web to the curb the exterior correction was fitted over.
#: Negative means the curb is inboard of the exterior web, which happens on the
#: narrow decks in this inventory.
CURB_DISTANCE_RANGE_FT: Final[tuple[float, float]] = (-1.0, 5.5)

#: The interior moment equation, AASHTO LRFD table 4.6.2.2.2b-1, k coefficients
#: for a concrete deck on steel beams. Every one of these came off that table
#: and none of them is derivable from anything else, which is why they are
#: written out one to a line rather than folded into the expression: the
#: question asked about a rating two years later is where a number came from.
ONE_LANE_INTERCEPT: Final[float] = 0.06
ONE_LANE_SPACING_FT: Final[float] = 14.0
ONE_LANE_SPACING_EXPONENT: Final[float] = 0.4
ONE_LANE_SPAN_EXPONENT: Final[float] = 0.3

TWO_LANE_INTERCEPT: Final[float] = 0.075
TWO_LANE_SPACING_FT: Final[float] = 9.5
TWO_LANE_SPACING_EXPONENT: Final[float] = 0.6
TWO_LANE_SPAN_EXPONENT: Final[float] = 0.2

#: The stiffness term's exponent, which is the same for one lane and two and is
#: the only part of the moment equation the shear equation drops.
STIFFNESS_EXPONENT: Final[float] = 0.1

#: The interior shear equation, table 4.6.2.2.3a-1. The two lane form is a
#: quadratic in the spacing rather than a power law, which is why it cannot be
#: written in the same shape as the moment one.
SHEAR_ONE_LANE_INTERCEPT: Final[float] = 0.36
SHEAR_ONE_LANE_DIVISOR_FT: Final[float] = 25.0
SHEAR_TWO_LANE_INTERCEPT: Final[float] = 0.2
SHEAR_TWO_LANE_DIVISOR_FT: Final[float] = 12.0
SHEAR_TWO_LANE_QUADRATIC_FT: Final[float] = 35.0

#: The exterior correction factors, tables 4.6.2.2.2d-1 and 4.6.2.2.3b-1. Two
#: different fits, which is the whole reason there are two functions.
MOMENT_E_INTERCEPT: Final[float] = 0.77
MOMENT_E_DIVISOR_FT: Final[float] = 9.1
SHEAR_E_INTERCEPT: Final[float] = 0.6
SHEAR_E_DIVISOR_FT: Final[float] = 10.0


def presence_factor(lanes_loaded: int) -> float:
    """Multiple presence factor for a number of loaded lanes."""
    if lanes_loaded < 1:
        raise InputError(f"{lanes_loaded} lanes loaded is not a load case")
    return PRESENCE_FACTORS.get(lanes_loaded, PRESENCE_FACTOR_MANY)


def apply_presence(raw_factor: float, lanes_loaded: int) -> float:
    """Multiply a statics based factor by the multiple presence factor.

    Never call this on the output of the approximate equations. They carry the
    factor already and applying it twice is a real mistake that has been made on
    this inventory before.
    """
    return raw_factor * presence_factor(lanes_loaded)


@dataclass(frozen=True, slots=True)
class GirderStiffness:
    """The longitudinal stiffness parameter and what it was built from.

    ``Kg`` is n times the sum of the girder inertia and its area times the
    eccentricity squared, where the eccentricity is centre of girder to centre
    of slab. It is the one term in the equations that carries the composite
    section, so it is passed in rather than guessed.
    """

    inertia_in4: float
    area_in2: float
    eccentricity_in: float
    modular_ratio: float

    def __post_init__(self) -> None:
        if self.inertia_in4 <= 0.0:
            raise InputError("girder inertia must be positive")
        if self.area_in2 <= 0.0:
            raise InputError("girder area must be positive")
        if self.modular_ratio <= 0.0:
            raise InputError("modular ratio must be positive")

    @property
    def kg_in4(self) -> float:
        """The longitudinal stiffness parameter."""
        transfer = self.area_in2 * self.eccentricity_in**2
        return self.modular_ratio * (self.inertia_in4 + transfer)


def _check_curb_distance(distance_to_curb_ft: float) -> None:
    """Refuse an overhang the e factors were not fitted for.

    Both fits share this range, and they used to check it twice with the
    numbers written out twice. Two copies of a range is one copy too many when
    one of them can be edited on its own.
    """
    low_ft, high_ft = CURB_DISTANCE_RANGE_FT
    if not low_ft <= distance_to_curb_ft <= high_ft:
        raise InputError(
            f"distance from web to curb {distance_to_curb_ft} ft is outside {low_ft} to {high_ft}"
        )


def _check_applicability(
    spacing_ft: float, span_ft: float, slab_in: float, kg_in4: float, beams: int
) -> None:
    low_ft, high_ft = SPACING_RANGE_FT
    if not low_ft <= spacing_ft <= high_ft:
        raise InputError(f"girder spacing {spacing_ft} ft is outside {low_ft} to {high_ft}")
    low_ft, high_ft = SPAN_RANGE_FT
    if not low_ft <= span_ft <= high_ft:
        raise InputError(f"span {span_ft} ft is outside {low_ft} to {high_ft}")
    low_in, high_in = SLAB_RANGE_IN
    if not low_in <= slab_in <= high_in:
        raise InputError(f"slab thickness {slab_in} in is outside {low_in} to {high_in}")
    low_k, high_k = STIFFNESS_RANGE_IN4
    if not low_k <= kg_in4 <= high_k:
        raise InputError(f"stiffness parameter {kg_in4:.0f} is outside {low_k:.0f} to {high_k:.0f}")
    if beams < MIN_BEAMS:
        raise InputError(f"{beams} beams is fewer than the {MIN_BEAMS} the equations assume")


def _stiffness_term(kg_in4: float, span_ft: float, slab_in: float) -> float:
    """The Kg term the moment equations carry and the shear ones do not."""
    return math.pow(kg_in4 / (12.0 * span_ft * math.pow(slab_in, 3.0)), STIFFNESS_EXPONENT)


def interior_moment(
    spacing_ft: float,
    span_ft: float,
    slab_in: float,
    stiffness: GirderStiffness,
    beams: int,
    *,
    lanes_loaded: int,
) -> float:
    """Moment distribution factor for an interior girder, in lanes per girder."""
    kg_in4 = stiffness.kg_in4
    _check_applicability(spacing_ft, span_ft, slab_in, kg_in4, beams)
    term = _stiffness_term(kg_in4, span_ft, slab_in)
    if lanes_loaded <= 1:
        shape = math.pow(spacing_ft / ONE_LANE_SPACING_FT, ONE_LANE_SPACING_EXPONENT) * math.pow(
            spacing_ft / span_ft, ONE_LANE_SPAN_EXPONENT
        )
        return ONE_LANE_INTERCEPT + shape * term
    shape = math.pow(spacing_ft / TWO_LANE_SPACING_FT, TWO_LANE_SPACING_EXPONENT) * math.pow(
        spacing_ft / span_ft, TWO_LANE_SPAN_EXPONENT
    )
    return TWO_LANE_INTERCEPT + shape * term


def interior_shear(spacing_ft: float, *, lanes_loaded: int) -> float:
    """Shear distribution factor for an interior girder.

    The shear equations carry no stiffness term at all, which is why a girder
    that fails in moment can still rate comfortably in shear.
    """
    low_ft, high_ft = SPACING_RANGE_FT
    if not low_ft <= spacing_ft <= high_ft:
        raise InputError(f"girder spacing {spacing_ft} ft is outside {low_ft} to {high_ft}")
    if lanes_loaded <= 1:
        return SHEAR_ONE_LANE_INTERCEPT + spacing_ft / SHEAR_ONE_LANE_DIVISOR_FT
    return (
        SHEAR_TWO_LANE_INTERCEPT
        + spacing_ft / SHEAR_TWO_LANE_DIVISOR_FT
        - math.pow(spacing_ft / SHEAR_TWO_LANE_QUADRATIC_FT, 2.0)
    )


def exterior_correction_moment(distance_to_curb_ft: float) -> float:
    """The e factor that turns an interior moment factor into an exterior one."""
    _check_curb_distance(distance_to_curb_ft)
    return max(1.0, MOMENT_E_INTERCEPT + distance_to_curb_ft / MOMENT_E_DIVISOR_FT)


def exterior_correction_shear(distance_to_curb_ft: float) -> float:
    """The e factor for shear, which is a different fit from the moment one."""
    _check_curb_distance(distance_to_curb_ft)
    return max(1.0, SHEAR_E_INTERCEPT + distance_to_curb_ft / SHEAR_E_DIVISOR_FT)


def lever_rule(spacing_ft: float, wheel_offsets_ft: list[float]) -> float:
    """Reaction on the exterior girder with the deck hinged at the first
    interior one.

    ``wheel_offsets_ft`` are wheel distances from the exterior girder, positive
    towards the interior. A wheel beyond the interior girder unloads the
    exterior one, so a negative contribution is kept rather than clipped.

    The answer is in wheel lines. Two wheel lines make a lane, so the caller
    halves it, and the multiple presence factor still has to be applied.
    """
    if spacing_ft <= 0.0:
        raise InputError(f"girder spacing {spacing_ft} is not a spacing")
    if not wheel_offsets_ft:
        raise InputError("the lever rule needs at least one wheel")
    return sum((spacing_ft - offset_ft) / spacing_ft for offset_ft in wheel_offsets_ft)
