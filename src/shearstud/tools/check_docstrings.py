"""Every module, public class, public function and public method says what it is.

The rule is not that a docstring exists. It is that the docstring says something
the signature does not, and that is not checkable, so this check does the part
that is: a docstring, on everything public, that is not a restatement of the
name with the underscores taken out.

The restatement test is crude and it catches the real cases. ``def
section_modulus_bottom_in3`` documented as "Section modulus bottom in3" tells a
reader nothing they did not have, and a check that lets that through is a check
that produces docstrings rather than documentation.
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
)

#: A docstring shorter than this is not a sentence.
MIN_DOCSTRING_CHARS: Final[int] = 12

#: Words a restatement is allowed to add without counting as new information.
FILLER: Final[frozenset[str]] = frozenset({"the", "a", "an", "of", "in", "for", "to", "is"})


def _restates(name: str, docstring: str) -> bool:
    """True when the docstring is the name with the underscores taken out."""
    from_name = {part for part in name.lower().split("_") if part}
    first = docstring.strip().split(".")[0].lower()
    words = {word.strip("`,;:()") for word in first.split()}
    extra = {word for word in words if word and word not in FILLER} - from_name
    return not extra


def _check_node(
    source: SourceFile, node: ast.FunctionDef | ast.ClassDef, what: str, problems: list[str]
) -> None:
    docstring = ast.get_docstring(node)
    where = f"{source.name}:{node.lineno}"
    if not docstring:
        problems.append(f"{where} {what} {node.name} has no docstring")
        return
    if len(docstring.strip()) < MIN_DOCSTRING_CHARS:
        problems.append(f"{where} {what} {node.name} has a docstring too short to say anything")
        return
    if _restates(node.name, docstring):
        problems.append(f"{where} {what} {node.name} restates its own name")


def problems() -> list[str]:
    """Everything public that is undocumented, or documented with its own name."""
    found: list[str] = []
    for source in source_files():
        if not ast.get_docstring(source.tree):
            found.append(f"{source.name} has no module docstring")
        for function in public_functions(source):
            _check_node(source, function, "function", found)
        for klass in public_classes(source):
            _check_node(source, klass, "class", found)
            for method in public_methods(klass):
                _check_node(source, method, "method", found)
    return found


def main() -> int:
    """Run the check and report."""
    return report("check_docstrings", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
