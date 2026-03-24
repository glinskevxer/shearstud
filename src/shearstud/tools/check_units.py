"""Every float that crosses a public boundary carries its unit in its name.

This is the check that makes ``shearstud.units`` a rule rather than a
convention. A public function parameter annotated ``float``, or a dataclass
field annotated ``float``, has to end in a registered unit suffix.

The exemptions are three named lists, not a pattern, because a pattern that let
any bare word through would defeat the check. ``growth`` and ``growth_pct`` are
different quantities and the second is the one this package means.

* **dimensionless** quantities. A ratio, a factor and a fraction are not
  measured in anything;
* **load effects**. A moment is kip feet and a shear is kips, and the rating
  code is deliberately written once for both. Naming the parameter
  ``effect_kipft`` would be a lie half the time it is called, so this family is
  exempt and the docstrings say which unit a given call is working in;
* **durations and counts**. Days, years and cycles are named in plain English
  throughout, and ``years_remaining_yr`` reads worse than it checks.

Private names and the ``self`` and ``cls`` conventions are exempt as well, for
the obvious reasons.
"""

from __future__ import annotations

import ast
import sys
from typing import Final

from shearstud.tools.walk import SourceFile, report, source_files
from shearstud.units import has_unit

#: Ratios, factors and fractions. Not measured in anything.
DIMENSIONLESS: Final[frozenset[str]] = frozenset(
    {
        "factor",
        "value",
        "ratio",
        "exponent",
        "allowance",
        "gauge_factor",
        "modular_ratio",
        "distribution_factor",
        "rating_factor",
        "governing_factor",
        "seasonal_factor",
        "slenderness",
        "web_slenderness",
        "k",
        "raw_factor",
        "condition",
        "system",
        "resistance",
        "tons",
        "adtt",
        "constant_a",
        "damage",
        "damage_already_done",
        "damage_per_first_year",
        "gamma_dc",
        "gamma_dw",
        "gamma_live",
        "fraction",
        "threshold",
        "logged_factor",
    }
)

#: Load effects, whose unit is kip feet for a moment and kips for a shear and is
#: decided by the influence line the caller built, not by the parameter.
LOAD_EFFECTS: Final[frozenset[str]] = frozenset(
    {
        "capacity",
        "component",
        "wearing_surface",
        "factored_dead",
        "factored_live",
        "static_effect",
        "static_truck",
        "truck_effect",
        "truck_with_impact",
        "lane",
        "lane_effect",
        "per_lane",
        "distributed",
        "live_effect",
        "nominal_capacity",
        "total_shear",
    }
)

#: Durations and counts, named in plain English throughout.
DURATIONS_AND_COUNTS: Final[frozenset[str]] = frozenset(
    {
        "count",
        "cycles",
        "cycles_counted",
        "cycles_per_passage",
        "days",
        "campaign_days",
        "annual_cycles",
        "years",
        "years_remaining",
        "fatigue_life_years",
        "half_window",
        "seconds",
    }
)

#: Names the language or a convention requires.
CONVENTIONAL: Final[frozenset[str]] = frozenset({"self", "cls"})

#: Every exemption, for the check itself and for the test that says they do not
#: overlap.
EXEMPT: Final[frozenset[str]] = DIMENSIONLESS | LOAD_EFFECTS | DURATIONS_AND_COUNTS | CONVENTIONAL


def _is_float(annotation: ast.expr | None) -> bool:
    """True when the annotation is exactly ``float``."""
    return isinstance(annotation, ast.Name) and annotation.id == "float"


def _needs_unit(name: str) -> bool:
    if name.startswith("_") or name in EXEMPT:
        return False
    return not has_unit(name)


def _check_function(source: SourceFile, node: ast.FunctionDef, problems: list[str]) -> None:
    if node.name.startswith("_"):
        return
    args = node.args
    every = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    for arg in every:
        if _is_float(arg.annotation) and _needs_unit(arg.arg):
            problems.append(
                f"{source.name}:{node.lineno} {node.name} takes a float {arg.arg!r} "
                f"with no unit suffix"
            )


def _check_class(source: SourceFile, node: ast.ClassDef, problems: list[str]) -> None:
    for item in node.body:
        if not isinstance(item, ast.AnnAssign) or not isinstance(item.target, ast.Name):
            continue
        name = item.target.id
        if _is_float(item.annotation) and _needs_unit(name):
            problems.append(
                f"{source.name}:{item.lineno} {node.name} has a float field {name!r} "
                f"with no unit suffix"
            )


def problems() -> list[str]:
    """Every public float that does not say what it is measured in."""
    found: list[str] = []
    for source in source_files():
        for node in ast.walk(source.tree):
            if isinstance(node, ast.FunctionDef):
                _check_function(source, node, found)
            elif isinstance(node, ast.ClassDef):
                _check_class(source, node, found)
    return found


def main() -> int:
    """Run the check and report."""
    return report("check_units", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
