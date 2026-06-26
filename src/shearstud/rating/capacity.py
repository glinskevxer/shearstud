"""Member capacity: what the girder can carry before the rating divides by it.

Three capacities are worked out here and they fail in different places, which is
why a rating has to compute all three rather than the one that looks worst on
the drawing:

* **yield moment** governs a slender or a non composite section, and is just the
  section modulus times the yield stress;
* **plastic moment** governs a compact composite section in positive bending,
  where the deck holds the top flange and the whole section can yield;
* **shear** governs short spans and the ends of everything, and on a girder with
  no transverse stiffeners it is the web buckling that decides, not the yield.

The compactness check that picks between the first two is the web slenderness
ratio, and it is written out rather than assumed because a girder built in 1962
is frequently not compact by today's rule even though it was by the rule it was
designed to.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from shearstud.errors import InputError
from shearstud.geometry.section import Section
from shearstud.units import STEEL_E_KSI, ft_to_in, kipin_to_kipft

#: Yield stresses this inventory holds, by the steel the drawing calls for.
YIELD_BY_GRADE_KSI: Final[dict[str, float]] = {
    "A7": 33.0,
    "A373": 32.0,
    "A36": 36.0,
    "A572-50": 50.0,
    "A709-50": 50.0,
    "A709-70": 70.0,
}

#: Web slenderness at or below which the web is compact, AASHTO LRFD 6.10.6.2.2
#: written with the constant folded in. Compared against D over tw.
COMPACT_WEB_COEFF: Final[float] = 3.76

#: Shear buckling coefficient for an unstiffened web.
UNSTIFFENED_SHEAR_K: Final[float] = 5.0

#: Ratio of shear yield to tensile yield used by the shear provisions.
SHEAR_YIELD_RATIO: Final[float] = 0.58

#: Which fibre a yield moment is taken about. ``governing`` means whichever of
#: the two yields first, which is what a bare steel section does and is the
#: only answer that is a moment the section can actually reach.
FIBRE_BOTTOM: Final[str] = "bottom"
FIBRE_TOP: Final[str] = "top"
FIBRE_GOVERNING: Final[str] = "governing"
FIBRES: Final[tuple[str, ...]] = (FIBRE_BOTTOM, FIBRE_TOP, FIBRE_GOVERNING)

#: The three coefficients of AASHTO LRFD 6.10.9.3.2, which decide whether the
#: web yields in shear, buckles inelastically, or buckles elastically. They are
#: the boundaries of the C factor and are the numbers a shear rating turns on.
SHEAR_YIELD_LIMIT_COEFF: Final[float] = 1.12
SHEAR_INELASTIC_LIMIT_COEFF: Final[float] = 1.40
SHEAR_ELASTIC_COEFF: Final[float] = 1.57


def yield_stress_ksi(grade: str) -> float:
    """Yield stress for a named steel grade."""
    key = grade.strip().upper()
    if key not in YIELD_BY_GRADE_KSI:
        raise InputError(f"unknown steel grade {grade!r}")
    return YIELD_BY_GRADE_KSI[key]


@dataclass(frozen=True, slots=True)
class FlexuralCapacity:
    """Moment capacity, and which mechanism decided it."""

    moment_kipft: float
    mechanism: str
    yield_stress_ksi: float
    is_compact: bool


def web_slenderness(section: Section) -> float:
    """Clear web depth over web thickness."""
    web = section.plate("web")
    return web.height_in / web.width_in


def is_compact_web(section: Section, fy_ksi: float) -> bool:
    """Whether the web is stocky enough to reach the plastic moment."""
    if fy_ksi <= 0.0:
        raise InputError(f"yield stress {fy_ksi} is not a stress")
    limit = COMPACT_WEB_COEFF * math.sqrt(STEEL_E_KSI / fy_ksi)
    return web_slenderness(section) <= limit


def yield_moment_kipft(section: Section, fy_ksi: float, *, fibre: str = FIBRE_GOVERNING) -> float:
    """First yield moment, at a nominated fibre or at whichever yields first.

    The default is the governing fibre and it is the default for a reason. On a
    singly symmetric girder the two section moduli differ by a third, and
    asking for the larger one reports a moment the section cannot reach,
    because the other flange yielded on the way there. A caller nominates a
    fibre only when something outside the bare section decides which one
    matters, which in this package means a deck holding the top flange.
    """
    if fy_ksi <= 0.0:
        raise InputError(f"yield stress {fy_ksi} is not a stress")
    if fibre == FIBRE_BOTTOM:
        modulus_in3 = section.section_modulus_bottom_in3
    elif fibre == FIBRE_TOP:
        modulus_in3 = section.section_modulus_top_in3
    elif fibre == FIBRE_GOVERNING:
        modulus_in3 = min(section.section_modulus_bottom_in3, section.section_modulus_top_in3)
    else:
        raise InputError(f"unknown fibre {fibre!r}, expected one of {FIBRES}")
    return kipin_to_kipft(modulus_in3 * fy_ksi)


def governing_fibre(section: Section) -> str:
    """Which fibre a bare section yields at first."""
    if section.section_modulus_top_in3 <= section.section_modulus_bottom_in3:
        return FIBRE_TOP
    return FIBRE_BOTTOM


def plastic_moment_kipft(section: Section, fy_ksi: float) -> float:
    """Full plastic moment of a steel section.

    The plastic neutral axis is found by equal areas rather than by the elastic
    centroid, so it is not the same axis the section modulus is taken about. On
    a singly symmetric girder the two are several inches apart.
    """
    if fy_ksi <= 0.0:
        raise InputError(f"yield stress {fy_ksi} is not a stress")
    axis_in = plastic_neutral_axis_in(section)
    total_kipin = 0.0
    for plate in section:
        # Both halves push the same way on the moment: the tension half pulls
        # below the axis and the compression half pushes above it, so the arm
        # is taken as a magnitude and the two add rather than cancel.
        for lo_in, hi_in in (
            (plate.y_bottom_in, min(plate.y_top_in, axis_in)),
            (max(plate.y_bottom_in, axis_in), plate.y_top_in),
        ):
            if hi_in <= lo_in:
                continue
            area_in2 = plate.width_in * (hi_in - lo_in)
            arm_in = abs((hi_in + lo_in) / 2.0 - axis_in)
            total_kipin += area_in2 * arm_in * fy_ksi
    return kipin_to_kipft(total_kipin)


def plastic_neutral_axis_in(section: Section) -> float:
    """Height at which half the area is above and half below.

    The area sweep is the section's own, so this is a search over the plate
    boundaries rather than a second implementation of the same arithmetic.
    """
    target_in2 = section.area_in2 / 2.0
    for lower_in, upper_in in pairwise(section.plate_edges_in()):
        if section.area_below_in2(upper_in) >= target_in2:
            width_in = section.width_at_in((lower_in + upper_in) / 2.0)
            if width_in <= 0.0:
                continue
            shortfall_in2 = target_in2 - section.area_below_in2(lower_in)
            return lower_in + shortfall_in2 / width_in
    return section.y_top_in


def flexural_capacity(
    section: Section, grade: str, *, composite: bool, fibre: str = FIBRE_GOVERNING
) -> FlexuralCapacity:
    """Moment capacity under the mechanism that governs.

    ``composite`` says the deck holds the top flange, which is what lets a
    compact section reach its plastic moment. Without it the section is bare
    steel, both flanges are free to yield, and the capacity is the first yield
    moment at whichever fibre gets there first.
    """
    fy_ksi = yield_stress_ksi(grade)
    compact = is_compact_web(section, fy_ksi)
    if composite and compact:
        return FlexuralCapacity(
            moment_kipft=plastic_moment_kipft(section, fy_ksi),
            mechanism="plastic",
            yield_stress_ksi=fy_ksi,
            is_compact=True,
        )
    return FlexuralCapacity(
        moment_kipft=yield_moment_kipft(section, fy_ksi, fibre=fibre),
        mechanism="yield",
        yield_stress_ksi=fy_ksi,
        is_compact=compact,
    )


def shear_capacity_kip(
    section: Section, grade: str, stiffener_spacing_ft: float | None = None
) -> float:
    """Web shear capacity, buckling accounted for.

    ``stiffener_spacing_ft`` of ``None`` means an unstiffened web, which is the
    common case on the older stringers and the one that buckles first.
    """
    fy_ksi = yield_stress_ksi(grade)
    web = section.plate("web")
    depth_in = web.height_in
    thickness_in = web.width_in
    plastic_kip = SHEAR_YIELD_RATIO * fy_ksi * depth_in * thickness_in
    if stiffener_spacing_ft is None:
        k = UNSTIFFENED_SHEAR_K
    else:
        if stiffener_spacing_ft <= 0.0:
            raise InputError(f"stiffener spacing {stiffener_spacing_ft} is not a spacing")
        ratio = ft_to_in(stiffener_spacing_ft) / depth_in
        k = UNSTIFFENED_SHEAR_K + UNSTIFFENED_SHEAR_K / (ratio * ratio)
    return plastic_kip * shear_buckling_ratio(depth_in / thickness_in, fy_ksi, k)


def shear_buckling_ratio(slenderness: float, fy_ksi: float, k: float) -> float:
    """The C factor: how much of the plastic shear the web can actually reach."""
    if slenderness <= 0.0:
        raise InputError(f"web slenderness {slenderness} is not a ratio")
    if fy_ksi <= 0.0:
        raise InputError(f"yield stress {fy_ksi} is not a stress")
    if k <= 0.0:
        raise InputError(f"buckling coefficient {k} is not a coefficient")
    yield_limit = SHEAR_YIELD_LIMIT_COEFF * math.sqrt(STEEL_E_KSI * k / fy_ksi)
    inelastic_limit = SHEAR_INELASTIC_LIMIT_COEFF * math.sqrt(STEEL_E_KSI * k / fy_ksi)
    if slenderness <= yield_limit:
        return 1.0
    if slenderness <= inelastic_limit:
        return yield_limit / slenderness
    return SHEAR_ELASTIC_COEFF * STEEL_E_KSI * k / (slenderness * slenderness * fy_ksi)
