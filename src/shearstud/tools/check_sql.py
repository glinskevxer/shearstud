"""SQL is parameterised, lives in the store layer, and names its columns.

Three rules, and the first one is the only one anybody would call security:

* **no value is ever interpolated into a statement.** A statement built with an
  f-string that carries anything but a table or column name this package chose
  itself is an injection. The check allows an f-string whose only interpolations
  name module level constants, because that is how the version table and the
  column lists are written, and refuses everything else;
* **SQL lives in the store layer.** A query in the rating code is a layering
  break the import check cannot see, because it needs no import;
* **no ``SELECT *``.** A star select breaks the day somebody adds a column, and
  it breaks by reading the wrong field rather than by raising.

The first rule is checked on the shape of the syntax tree rather than on the
text, so a statement assembled across three lines is still seen as one.

SQLite will not take a table name as a parameter, so a handful of functions have
to interpolate one. Rather than an allow list here, which goes quiet the day
somebody adds a twelfth function to it, each module names its own: a top level
``SQL_NAME_INTERPOLATION`` tuple listing the functions in that module which
validate the identifier against the real schema before building the statement.
The check reads that constant out of the module it is checking, so the list
cannot drift away from the code it describes.

The tools layer is exempt from all three rules. It holds SQL keywords as
patterns to look for, and a check that fails on its own regular expression is a
check nobody keeps.
"""

from __future__ import annotations

import ast
import re
import sys
from typing import Final

from shearstud.tools.walk import SourceFile, report, source_files

#: Layers allowed to hold SQL.
SQL_LAYERS: Final[frozenset[str]] = frozenset({"store"})

#: Layers this check does not look at.
EXEMPT_LAYERS: Final[frozenset[str]] = frozenset({"tools"})

#: Name of the constant a module uses to declare the functions that may
#: interpolate a validated identifier.
OPT_OUT_CONSTANT: Final[str] = "SQL_NAME_INTERPOLATION"

#: What makes a string look like a statement.
STATEMENT: Final[re.Pattern[str]] = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE TABLE|CREATE INDEX|PRAGMA)\b"
)

#: A star select, which this package never wants.
STAR_SELECT: Final[re.Pattern[str]] = re.compile(r"SELECT\s+\*", re.IGNORECASE)


def _module_constants(source: SourceFile) -> set[str]:
    """Top level names assigned in upper case, which are this package's own."""
    out: set[str] = set()
    for node in source.tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                out.add(target.id)
    return out


def _is_statement(text: str) -> bool:
    return bool(STATEMENT.search(text))


def _joined_text(node: ast.JoinedStr) -> str:
    return "".join(
        part.value
        for part in node.values
        if isinstance(part, ast.Constant) and isinstance(part.value, str)
    )


def _declared_opt_outs(source: SourceFile) -> set[str]:
    """Functions the module itself says validate their identifier first."""
    for node in source.tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            names_the_constant = isinstance(target, ast.Name) and target.id == OPT_OUT_CONSTANT
            if names_the_constant and isinstance(node.value, ast.Tuple | ast.List):
                return {
                    element.value
                    for element in node.value.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                }
    return set()


def _enclosing_functions(source: SourceFile) -> dict[int, str]:
    """Line number to the function that line is inside."""
    out: dict[int, str] = {}
    for node in ast.walk(source.tree):
        if isinstance(node, ast.FunctionDef):
            end = node.end_lineno or node.lineno
            for line in range(node.lineno, end + 1):
                out[line] = node.name
    return out


def _interpolated_names(node: ast.JoinedStr) -> list[str]:
    out: list[str] = []
    for part in node.values:
        if isinstance(part, ast.FormattedValue):
            out.append(ast.unparse(part.value))
    return out


def problems() -> list[str]:
    """Interpolated statements, SQL outside the store, and star selects."""
    found: list[str] = []
    for source in source_files(include_tools=True):
        if source.layer in EXEMPT_LAYERS:
            continue
        constants = _module_constants(source)
        opted_out = _declared_opt_outs(source)
        enclosing = _enclosing_functions(source)
        for node in ast.walk(source.tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
                if not _is_statement(text):
                    continue
                if source.layer not in SQL_LAYERS:
                    found.append(f"{source.name}:{node.lineno} holds SQL outside the store layer")
                if STAR_SELECT.search(text):
                    found.append(f"{source.name}:{node.lineno} uses SELECT *")
            elif isinstance(node, ast.JoinedStr):
                text = _joined_text(node)
                if not _is_statement(text):
                    continue
                if source.layer not in SQL_LAYERS:
                    found.append(f"{source.name}:{node.lineno} holds SQL outside the store layer")
                if STAR_SELECT.search(text):
                    found.append(f"{source.name}:{node.lineno} uses SELECT *")
                if enclosing.get(node.lineno) in opted_out:
                    continue
                for name in _interpolated_names(node):
                    if name not in constants:
                        found.append(
                            f"{source.name}:{node.lineno} interpolates {name!r} into a "
                            f"statement, which only a module constant may be"
                        )
    return found


def statement_count() -> int:
    """How many SQL statements the package holds, for the architecture page."""
    total = 0
    for source in source_files(include_tools=True):
        if source.layer in EXEMPT_LAYERS:
            continue
        for node in ast.walk(source.tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                total += 1 if _is_statement(node.value) else 0
            elif isinstance(node, ast.JoinedStr):
                total += 1 if _is_statement(_joined_text(node)) else 0
    return total


def main() -> int:
    """Run the check and report."""
    return report("check_sql", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
