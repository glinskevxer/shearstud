"""A coefficient buried in an expression is a coefficient nobody can check.

Every number in this package that came out of a specification has a name, a
module level constant, and a comment saying which clause it is from. That is not
tidiness. A rating is a number somebody signs, and the question that gets asked
about it two years later is "where did the 1.35 come from", which is answerable
in a second if the answer is a named constant and takes an afternoon if it is
the fourth term of a division inside a loop.

So this walks the domain layers and reports float literals inside function
bodies. Module level assignments are fine, because that is what a named constant
looks like. The arithmetic identities are fine too, and so are the small
integers that are counting rather than measuring.

What it deliberately does not do is guess. It cannot tell a coefficient from a
conversion, so it reports both and the exemption list carries the ones that are
genuinely not coefficients. The list is short and every entry says why.
"""

from __future__ import annotations

import ast
import sys
from typing import Final

from shearstud.tools.walk import SourceFile, report, source_files

#: Layers held to this. The tools and the command line are excluded: a CLI
#: default is a default and belongs where the option is declared, and the tools
#: are not domain code.
CHECKED_LAYERS: Final[frozenset[str]] = frozenset(
    {"geometry", "loads", "signals", "fatigue", "structure", "rating", "program"}
)

#: Values that mean something arithmetic rather than something physical.
#: ``0.5`` is a half and ``2.0`` is a double; neither came out of a code book.
IDENTITIES: Final[frozenset[float]] = frozenset({0.0, 1.0, 2.0, 0.5, 100.0, -1.0})

#: Numbers whose meaning is in the expression around them rather than in a
#: specification. Each of these is a unit conversion or a tolerance that is
#: written where it is used because naming it would put the definition further
#: from the arithmetic than the arithmetic is long.
EXEMPT_VALUES: Final[frozenset[float]] = frozenset(
    {
        12.0,  # inches per foot, and everybody knows it
        360.0,  # degrees in a circle
        1000.0,  # kips to pounds
        1.0e-6,  # microstrain to strain
        1.0e-9,  # a tolerance on a comparison, not a physical quantity
        1.0e-12,  # the same, one order tighter
        3.0,  # three points of a three point rule, counting rather than measuring
        4.0,  # four points of the four point rainflow rule
    }
)


def literals(source: SourceFile) -> list[tuple[int, float]]:
    """Every float literal in a function body in this file, with its line.

    The body and not the whole definition. Walking the definition reaches the
    default arguments, which are part of the signature rather than of the
    arithmetic, and reporting one of those says a named constant is wanted for
    a number that is already named by the parameter it defaults.
    """
    out: list[tuple[int, float]] = []
    for node in ast.walk(source.tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for statement in node.body:
            for inner in ast.walk(statement):
                if not isinstance(inner, ast.Constant):
                    continue
                if isinstance(inner.value, bool) or not isinstance(inner.value, float):
                    continue
                out.append((inner.lineno, float(inner.value)))
    return out


def defaults(source: SourceFile) -> set[float]:
    """Float literals that are a function's own default argument.

    A default is part of the signature and reads as one. It is visible in the
    help, in the docstring and at every call site that overrides it, which is
    the whole thing a named constant buys.

    A leading minus is stripped, so ``-0.25`` is collected as ``0.25``. That is
    not sloppiness about the sign: the parser puts the sign in an operator and
    the number in the constant, in a default and in an expression alike, so
    comparing the constants is comparing like with like.
    """
    out: set[float] = set()
    for node in ast.walk(source.tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for value in [*node.args.defaults, *node.args.kw_defaults]:
            for inner in ast.walk(value) if value is not None else []:
                if isinstance(inner, ast.Constant) and isinstance(inner.value, float):
                    out.add(float(inner.value))
    return out


def problems() -> list[str]:
    """Every float in a function body that should have been a named constant."""
    found: list[str] = []
    for source in source_files():
        if source.layer not in CHECKED_LAYERS:
            continue
        allowed = IDENTITIES | EXEMPT_VALUES | defaults(source)
        seen: set[tuple[int, float]] = set()
        for line, value in literals(source):
            if value in allowed or (line, value) in seen:
                continue
            seen.add((line, value))
            found.append(f"{source.name}:{line} the literal {value:g} wants a name and a clause")
    return found


def counts() -> dict[str, int]:
    """How many literals each checked layer carries, exempt ones included."""
    out: dict[str, int] = {}
    for source in source_files():
        if source.layer not in CHECKED_LAYERS:
            continue
        out[source.layer] = out.get(source.layer, 0) + len(literals(source))
    return out


def main(argv: list[str] | None = None) -> int:
    """Run the check and report."""
    if argv is not None and "--counts" in argv:
        for layer, count in sorted(counts().items()):
            print(f"check_constants: {layer} carries {count} float literal(s)")
    return report("check_constants", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
