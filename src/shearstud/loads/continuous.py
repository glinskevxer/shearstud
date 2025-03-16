"""Influence lines for continuous units, from the three moment equation.

A continuous unit cannot be handled span by span. A load in the back span
changes the moment over the pier and therefore the moment everywhere, which is
exactly why continuity is worth having and exactly why the analysis is more than
arithmetic.

The method here is the classical one. For a unit load at a given position, the
three moment equation gives a tridiagonal system in the interior support
moments; solving it and adding the simple span terms gives the load effect at
any section. Sweeping the load position across the unit gives the influence
line.

Two approximations are made on purpose and neither is hidden:

* prismatic spans, so a flange transition inside a span is ignored for the
  purpose of distributing moment between spans. Section changes on these units
  are small and near the piers, and the error is well under the modelling
  uncertainty already carried by the distribution factors;
* the influence line comes back sampled and joined by straight lines. The true
  line is piecewise cubic in load position, so the sample step is a real
  parameter and not a detail.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from shearstud.errors import InputError
from shearstud.loads.influence import InfluenceLine, line

#: Default number of load positions across the whole unit. A cubic sampled this
#: finely and joined by chords is inside a tenth of a percent on every span
#: arrangement in this inventory.
DEFAULT_SAMPLES: Final[int] = 400

#: How far either side of a section the shear line is evaluated to get its two
#: limits. Small enough not to move the answer, large enough to survive the
#: subtraction in double precision.
SHEAR_EPSILON_FT: Final[float] = 1.0e-6


def _check_lengths(lengths_ft: Sequence[float]) -> None:
    if not lengths_ft:
        raise InputError("a continuous unit needs at least one span")
    for index, length_ft in enumerate(lengths_ft):
        if length_ft <= 0.0:
            raise InputError(f"span {index} is {length_ft} ft, which is not a span")


def _solve_tridiagonal(
    below: Sequence[float], diagonal: Sequence[float], above: Sequence[float], rhs: Sequence[float]
) -> list[float]:
    """Thomas algorithm. The system from the three moment equation is always
    diagonally dominant, so no pivoting is needed."""
    n = len(diagonal)
    if n == 0:
        return []
    c = list(above)
    d = list(rhs)
    b = list(diagonal)
    for i in range(1, n):
        factor = below[i] / b[i - 1]
        b[i] -= factor * c[i - 1]
        d[i] -= factor * d[i - 1]
    out = [0.0] * n
    out[-1] = d[-1] / b[-1]
    for i in range(n - 2, -1, -1):
        out[i] = (d[i] - c[i] * out[i + 1]) / b[i]
    return out


def support_moments(
    lengths_ft: Sequence[float], load_span: int, load_local_ft: float, load_kip: float = 1.0
) -> list[float]:
    """Bending moment at every support for one point load.

    Returns one value per support, both abutments included, sagging positive.
    The abutment values are zero because these units are simply supported at
    their ends; a fixed end would be a different structure.
    """
    _check_lengths(lengths_ft)
    span_count = len(lengths_ft)
    if not 0 <= load_span < span_count:
        raise InputError(f"no span {load_span} in a {span_count} span unit")
    if not 0.0 <= load_local_ft <= lengths_ft[load_span]:
        raise InputError(
            f"load at {load_local_ft} ft is not on span {load_span}, "
            f"which is {lengths_ft[load_span]} ft"
        )
    interior = span_count - 1
    if interior <= 0:
        return [0.0, 0.0]

    below = [0.0] * interior
    diagonal = [0.0] * interior
    above = [0.0] * interior
    rhs = [0.0] * interior
    for row in range(interior):
        left_len_ft = lengths_ft[row]
        right_len_ft = lengths_ft[row + 1]
        diagonal[row] = 2.0 * (left_len_ft + right_len_ft)
        if row > 0:
            below[row] = left_len_ft
        if row < interior - 1:
            above[row] = right_len_ft
        load = 0.0
        if load_span == row:
            a_ft = load_local_ft
            load += load_kip * a_ft * (left_len_ft**2 - a_ft**2) / left_len_ft
        if load_span == row + 1:
            b_ft = right_len_ft - load_local_ft
            load += load_kip * b_ft * (right_len_ft**2 - b_ft**2) / right_len_ft
        rhs[row] = -load

    solved = _solve_tridiagonal(below, diagonal, above, rhs)
    return [0.0, *solved, 0.0]


def moment_at(
    lengths_ft: Sequence[float],
    section_span: int,
    section_local_ft: float,
    load_span: int,
    load_local_ft: float,
    load_kip: float = 1.0,
) -> float:
    """Bending moment at one section for one point load."""
    moments = support_moments(lengths_ft, load_span, load_local_ft, load_kip)
    span_len_ft = lengths_ft[section_span]
    left_kipft = moments[section_span]
    right_kipft = moments[section_span + 1]
    fraction = section_local_ft / span_len_ft
    continuity = left_kipft * (1.0 - fraction) + right_kipft * fraction
    simple = 0.0
    if load_span == section_span:
        a_ft = load_local_ft
        b_ft = span_len_ft - a_ft
        if section_local_ft <= a_ft:
            simple = load_kip * b_ft * section_local_ft / span_len_ft
        else:
            simple = load_kip * a_ft * (span_len_ft - section_local_ft) / span_len_ft
    return simple + continuity


def shear_at(
    lengths_ft: Sequence[float],
    section_span: int,
    section_local_ft: float,
    load_span: int,
    load_local_ft: float,
    load_kip: float = 1.0,
) -> float:
    """Shear at one section for one point load.

    Positive shear is the left part of the beam pushing the right part up, the
    same convention the simple span lines use.
    """
    moments = support_moments(lengths_ft, load_span, load_local_ft, load_kip)
    span_len_ft = lengths_ft[section_span]
    continuity = (moments[section_span + 1] - moments[section_span]) / span_len_ft
    simple = 0.0
    if load_span == section_span:
        a_ft = load_local_ft
        b_ft = span_len_ft - a_ft
        simple = load_kip * b_ft / span_len_ft
        if section_local_ft > a_ft:
            simple -= load_kip
    return simple + continuity


def _sweep_stations(lengths_ft: Sequence[float], samples: int) -> list[float]:
    """Load positions to evaluate at: an even grid plus every support."""
    total_ft = sum(lengths_ft)
    step_ft = total_ft / samples
    stations = [i * step_ft for i in range(samples + 1)]
    running_ft = 0.0
    for length_ft in lengths_ft[:-1]:
        running_ft += length_ft
        stations.append(running_ft)
    return sorted(set(stations))


def _to_local(lengths_ft: Sequence[float], global_ft: float) -> tuple[int, float]:
    running_ft = 0.0
    for index, length_ft in enumerate(lengths_ft):
        if global_ft <= running_ft + length_ft:
            return index, global_ft - running_ft
        running_ft += length_ft
    return len(lengths_ft) - 1, lengths_ft[-1]


def _global_of(lengths_ft: Sequence[float], span_index: int, local_ft: float) -> float:
    return sum(lengths_ft[:span_index]) + local_ft


def continuous_moment(
    lengths_ft: Sequence[float],
    section_span: int,
    section_local_ft: float,
    samples: int = DEFAULT_SAMPLES,
) -> InfluenceLine:
    """Moment influence line at a section of a continuous unit."""
    _check_lengths(lengths_ft)
    if samples < len(lengths_ft) * 4:
        raise InputError(f"{samples} samples is too coarse for {len(lengths_ft)} spans")
    points: list[tuple[float, float]] = []
    for station_ft in _sweep_stations(lengths_ft, samples):
        load_span, local_ft = _to_local(lengths_ft, station_ft)
        value = moment_at(lengths_ft, section_span, section_local_ft, load_span, local_ft)
        points.append((station_ft, value))
    label = f"M at span {section_span} + {section_local_ft:g}"
    return line(label, points)


def continuous_shear(
    lengths_ft: Sequence[float],
    section_span: int,
    section_local_ft: float,
    samples: int = DEFAULT_SAMPLES,
) -> InfluenceLine:
    """Shear influence line at a section of a continuous unit.

    The jump at the section is put in explicitly, by evaluating either side of
    it and placing both values at the section's own station.
    """
    _check_lengths(lengths_ft)
    if samples < len(lengths_ft) * 4:
        raise InputError(f"{samples} samples is too coarse for {len(lengths_ft)} spans")
    section_global_ft = _global_of(lengths_ft, section_span, section_local_ft)
    points: list[tuple[float, float]] = []
    for station_ft in _sweep_stations(lengths_ft, samples):
        if abs(station_ft - section_global_ft) < SHEAR_EPSILON_FT:
            continue
        load_span, local_ft = _to_local(lengths_ft, station_ft)
        value = shear_at(lengths_ft, section_span, section_local_ft, load_span, local_ft)
        points.append((station_ft, value))
    for offset_ft in (-SHEAR_EPSILON_FT, SHEAR_EPSILON_FT):
        probe_ft = min(max(section_global_ft + offset_ft, 0.0), sum(lengths_ft))
        load_span, local_ft = _to_local(lengths_ft, probe_ft)
        value = shear_at(lengths_ft, section_span, section_local_ft, load_span, local_ft)
        points.append((section_global_ft, value))
    points.sort(key=lambda p: (p[0], 0.0))
    label = f"V at span {section_span} + {section_local_ft:g}"
    return line(label, points)


def continuous_support_moment(
    lengths_ft: Sequence[float], support_index: int, samples: int = DEFAULT_SAMPLES
) -> InfluenceLine:
    """Moment influence line at an interior support."""
    _check_lengths(lengths_ft)
    if not 1 <= support_index <= len(lengths_ft) - 1:
        raise InputError(f"support {support_index} is not an interior support")
    return continuous_moment(lengths_ft, support_index - 1, lengths_ft[support_index - 1], samples)
