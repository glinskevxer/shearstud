"""Miner damage from a measured spectrum, and the infinite life question.

Two questions get asked of a measured spectrum and they are not the same one:

* **does this detail last forever?** Answered by comparing the effective stress
  range against a fraction of the constant amplitude threshold. The fraction is
  there because a measured spectrum has a tail, and a detail whose *average*
  cycle is under the threshold can still be driven by the handful of cycles
  above it;
* **if not, how long?** Answered by summing the damage from every bin, which is
  Miner's rule, and inverting it.

Below the threshold the S-N curve does not really stop, it gets shallower. This
module takes the conservative reading and counts every cycle on the single
sloping curve, so a spectrum full of small cycles is charged for them. The
alternative, dropping everything under the threshold, has been measured on this
inventory to change a remaining life by a factor of three on a quiet detail, and
the conservative direction is the one a rating goes in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from shearstud.errors import InputError
from shearstud.fatigue.categories import CURVE_EXPONENT, DetailCategory
from shearstud.signals.spectrum import Spectrum
from shearstud.units import STEEL_E_KSI, strain_to_stress_ksi

#: Fraction of the constant amplitude threshold that a measured effective range
#: has to stay under before the detail is called infinite life. AASHTO MBE uses
#: one half, which allows for the tail of a real spectrum.
DEFAULT_TRUNCATION_FRAC: Final[float] = 0.5


@dataclass(frozen=True, slots=True)
class DamageResult:
    """What a spectrum did to one detail."""

    detail_category: str
    cycles_counted: float
    effective_range_ksi: float
    largest_range_ksi: float
    damage: float
    infinite_life: bool

    @property
    def is_damaged(self) -> bool:
        """True when any damage at all accumulated."""
        return self.damage > 0.0

    def cycles_remaining(self) -> float:
        """How many more spectra like this one the detail has left.

        Infinite when the detail is infinite life, which is a real answer and
        not a missing one.
        """
        if self.infinite_life:
            return math.inf
        if self.damage <= 0.0:
            return math.inf
        return (1.0 - self.damage) / self.damage


def stress_bins_ksi(
    spectrum: Spectrum, modulus_ksi: float = STEEL_E_KSI
) -> list[tuple[float, float]]:
    """Spectrum bins converted to stress range and count."""
    if modulus_ksi <= 0.0:
        raise InputError(f"modulus {modulus_ksi} is not a modulus")
    return [
        (strain_to_stress_ksi(b.representative_ue, modulus_ksi), b.count)
        for b in spectrum.bins
        if b.count > 0.0
    ]


def effective_range_ksi(
    spectrum: Spectrum,
    modulus_ksi: float = STEEL_E_KSI,
    exponent: float = CURVE_EXPONENT,
) -> float:
    """The single stress range that does the same damage as the spectrum."""
    if exponent <= 0.0:
        raise InputError(f"exponent {exponent} is not positive")
    bins = stress_bins_ksi(spectrum, modulus_ksi)
    total = sum(count for _, count in bins)
    if total <= 0.0:
        return 0.0
    weighted = sum(count * math.pow(range_ksi, exponent) for range_ksi, count in bins)
    return math.pow(weighted / total, 1.0 / exponent)


def largest_range_ksi(spectrum: Spectrum, modulus_ksi: float = STEEL_E_KSI) -> float:
    """The biggest stress range the spectrum holds."""
    bins = stress_bins_ksi(spectrum, modulus_ksi)
    if not bins:
        return 0.0
    return max(range_ksi for range_ksi, _ in bins)


def has_infinite_life(
    spectrum: Spectrum,
    detail: DetailCategory,
    modulus_ksi: float = STEEL_E_KSI,
    truncation_frac: float = DEFAULT_TRUNCATION_FRAC,
) -> bool:
    """Whether the detail survives this spectrum indefinitely."""
    if not 0.0 < truncation_frac <= 1.0:
        raise InputError(f"truncation fraction {truncation_frac} is outside zero to one")
    effective = effective_range_ksi(spectrum, modulus_ksi)
    return effective < truncation_frac * detail.threshold_ksi


def accumulate(
    spectrum: Spectrum,
    detail: DetailCategory,
    modulus_ksi: float = STEEL_E_KSI,
    truncation_frac: float = DEFAULT_TRUNCATION_FRAC,
) -> DamageResult:
    """Miner damage from one spectrum at one detail."""
    bins = stress_bins_ksi(spectrum, modulus_ksi)
    total = sum(count for _, count in bins)
    damage = 0.0
    for range_ksi, count in bins:
        if range_ksi <= 0.0:
            continue
        life = detail.constant_a / math.pow(range_ksi, CURVE_EXPONENT)
        damage += count / life
    infinite = has_infinite_life(spectrum, detail, modulus_ksi, truncation_frac)
    return DamageResult(
        detail_category=detail.name,
        cycles_counted=total,
        effective_range_ksi=effective_range_ksi(spectrum, modulus_ksi),
        largest_range_ksi=largest_range_ksi(spectrum, modulus_ksi),
        damage=0.0 if infinite else damage,
        infinite_life=infinite,
    )


def combine(results: list[DamageResult]) -> float:
    """Total damage from several spectra at the same detail.

    Miner's rule is linear and order independent, which is exactly why a
    sequence of measurement campaigns can be added up. Infinite life results
    contribute nothing.
    """
    return sum(result.damage for result in results)


def damage_per_cycle(range_ksi: float, detail: DetailCategory) -> float:
    """Damage one cycle of a given range does at a given detail."""
    if range_ksi <= 0.0:
        raise InputError(f"stress range {range_ksi} is not a range")
    return math.pow(range_ksi, CURVE_EXPONENT) / detail.constant_a
