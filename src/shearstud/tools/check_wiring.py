"""Nothing public is written and then left with no caller.

A module with a green test file and no caller anywhere is not tested where it
matters. The test proves the function computes what its author had in mind; it
proves nothing about whether the number ever reaches a rating. That gap is easy
to open and almost impossible to see in review, because both halves look right
on their own.

So this walks every public definition in the application source and asks whether
its name is used anywhere else at all: another module, or a test. The rule is
deliberately loose about *how* it is used. Trying to resolve a call to the
definition it lands on would need a type checker, and a check that is nearly a
type checker is a check nobody trusts. A name mentioned somewhere else is enough
to say the code is wired; a name mentioned nowhere is unambiguous.

Three consequences of the looseness are worth stating rather than hiding. Two
functions with the same name in different modules cover for each other, so this
will not catch one of a matched pair going dead. A decorated definition is taken
as wired without any mention, because a decorator is how a command is registered
and the registration is the wiring. And a class named in a return annotation in
its own module is taken as wired, because a result type is reached through the
function that builds it and never by name. That last one does not open a hole:
if the function that returns it has no caller either, the function is on the
list and the whole chain is dead in one report.
"""

from __future__ import annotations

import ast
import sys
from typing import Final

from shearstud.tools.walk import (
    SourceFile,
    public_classes,
    public_functions,
    public_methods,
    report,
    source_files,
    suite_files,
)

#: Names that exist to satisfy an interface rather than to be called by us.
#: ``main`` is the entry point of every tool, and the dunder methods are called
#: by the interpreter and never by name.
INTERFACE_NAMES: Final[frozenset[str]] = frozenset({"main"})

#: Methods a dataclass or a protocol is expected to carry.
PROTOCOL_METHODS: Final[frozenset[str]] = frozenset({"keys", "values", "items"})


def used_names(source: SourceFile) -> set[str]:
    """Every identifier this file mentions, however it mentions it."""
    out: set[str] = set()
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                out.add(alias.name)
    return out


def returned_types(source: SourceFile) -> set[str]:
    """Every name a function or method in this file says it returns."""
    out: set[str] = set()
    for node in ast.walk(source.tree):
        if not isinstance(node, ast.FunctionDef) or node.returns is None:
            continue
        for part in ast.walk(node.returns):
            if isinstance(part, ast.Name):
                out.add(part.id)
            elif isinstance(part, ast.Attribute):
                out.add(part.attr)
            elif isinstance(part, ast.Constant) and isinstance(part.value, str):
                out.add(part.value)
    return out


def _definitions(source: SourceFile) -> list[tuple[int, str, str]]:
    """Every public definition in a file, as line, kind and name."""
    out: list[tuple[int, str, str]] = []
    for node in public_functions(source):
        if node.decorator_list:
            continue
        out.append((node.lineno, "function", node.name))
    for klass in public_classes(source):
        out.append((klass.lineno, "class", klass.name))
        for method in public_methods(klass):
            if method.name in PROTOCOL_METHODS:
                continue
            out.append((method.lineno, "method", method.name))
    return out


def vocabulary() -> dict[str, set[str]]:
    """Which files mention each identifier, keyed by identifier."""
    out: dict[str, set[str]] = {}
    for source in [*source_files(include_tools=True), *suite_files()]:
        for name in used_names(source):
            out.setdefault(name, set()).add(source.name)
    return out


def problems() -> list[str]:
    """Every public definition nothing outside its own module mentions."""
    seen = vocabulary()
    found: list[str] = []
    for source in source_files():
        returned = returned_types(source)
        for line, kind, name in _definitions(source):
            if name in INTERFACE_NAMES:
                continue
            if kind == "class" and name in returned:
                continue
            elsewhere = seen.get(name, set()) - {source.name}
            if not elsewhere:
                found.append(f"{source.name}:{line} {kind} {name} has no caller and no test")
    return found


def unexercised() -> list[str]:
    """Public definitions the suite never mentions, which is a softer question.

    Something used by another module but named in no test is exercised through
    its caller. That is a real gap and a fair thing to know about, but it is not
    the same failure as dead code and it does not fail the check.
    """
    mentioned: set[str] = set()
    for suite in suite_files():
        mentioned |= used_names(suite)
    out: list[str] = []
    for source in source_files():
        for _, kind, name in _definitions(source):
            if name not in mentioned and name not in INTERFACE_NAMES:
                out.append(f"{source.name} {kind} {name}")
    return out


def main(argv: list[str] | None = None) -> int:
    """Run the check and report."""
    args = sys.argv[1:] if argv is None else argv
    found = problems()
    if "--unexercised" in args:
        for entry in unexercised():
            print(f"check_wiring: not named by any test: {entry}")
    return report("check_wiring", found)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
