"""The thresholds document: every number this package decides on, in one table.

There is a question a bridge engineer asks about any tool like this one and it
is not answerable by reading the source: what does it think the numbers are.
Not the arithmetic, the thresholds. At what condition rating does the interval
shorten, how much section loss is a finding, how far below one does a rating
factor have to be before the structure gets posted, how much of a record can
drop out before the count is thrown away.

Those are all module level constants with comments on them, so this collects
them and prints them. The comment is the part that matters, and it is why this
reads the source rather than importing the module: a value can be imported and
a ``#:`` comment cannot.

What is collected is deliberately narrow. A constant is a rule if its name ends
in one of a short list of suffixes that mean a boundary. A coefficient out of a
table is not a rule and would swamp the document; the distribution factor
exponents are correct and nobody argues about them, while the condition rating
that shortens an inspection interval is an agency decision somebody will want
to change.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from typing import Final

from shearstud.tools.generated import Document, run, table
from shearstud.tools.walk import SourceFile, source_files

DOCUMENT = Document(filename="rules.md", command="build_rules")

#: A constant is a rule when its name ends in one of these. Each one means a
#: boundary rather than a coefficient: something is on one side of it or the
#: other, and which side decides what happens next.
RULE_SUFFIXES: Final[tuple[str, ...]] = (
    "_LIMIT",
    "_THRESHOLD",
    "_MINIMUM",
    "_MAXIMUM",
    "_FLOOR",
    "_CEILING",
    "_TOLERANCE",
    "_RANGE",
    "_YEARS",
    "_MONTHS",
    "_RATING",
    "_POLICY",
)

#: Names that carry one of those suffixes and are not rules. Each is a unit or
#: a physical constant that happens to be spelled the same way.
NOT_A_RULE: Final[frozenset[str]] = frozenset({"STATION_TOLERANCE_FT"})

#: Prefixes that mean the same thing at the front of a name.
RULE_PREFIXES: Final[tuple[str, ...]] = ("MIN_", "MAX_")


@dataclass(frozen=True, slots=True)
class Rule:
    """One threshold, and what its author said about it."""

    module: str
    name: str
    value: str
    note: str

    @property
    def has_note(self) -> bool:
        """Whether the author left a comment on it."""
        return bool(self.note)


def is_rule(name: str) -> bool:
    """Whether a constant's name says it is a boundary."""
    if name in NOT_A_RULE or not name.isupper():
        return False
    if name.startswith(RULE_PREFIXES):
        return True
    return name.endswith(RULE_SUFFIXES)


def _note_above(source: SourceFile, line: int) -> str:
    """The ``#:`` comment block immediately above a line, as one sentence."""
    lines = source.lines()
    collected: list[str] = []
    index = line - 2
    while index >= 0:
        text = lines[index].strip()
        if not text.startswith("#:"):
            break
        collected.append(text[2:].strip())
        index -= 1
    return " ".join(reversed(collected))


def rules() -> list[Rule]:
    """Every threshold constant in the package, in module and name order."""
    out: list[Rule] = []
    for source in source_files():
        for node in source.tree.body:
            targets = _targets(node)
            for target, value in targets:
                if not is_rule(target):
                    continue
                out.append(
                    Rule(
                        module=source.module,
                        name=target,
                        value=ast.unparse(value),
                        note=_note_above(source, node.lineno),
                    )
                )
    return sorted(out, key=lambda rule: (rule.module, rule.name))


def _targets(node: ast.stmt) -> list[tuple[str, ast.expr]]:
    """The name and value of a module level constant assignment."""
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [] if node.value is None else [(node.target.id, node.value)]
    if isinstance(node, ast.Assign):
        return [(target.id, node.value) for target in node.targets if isinstance(target, ast.Name)]
    return []


def body() -> str:
    """The document."""
    found = rules()
    rows = [[rule.module, rule.name, f"`{rule.value}`", rule.note] for rule in found]
    return "\n".join(
        [
            "# Thresholds",
            "",
            "Every number this package decides on: the boundaries, not the",
            "coefficients. A coefficient out of a specification table is correct and",
            "nobody argues about it. These are the ones an agency changes.",
            "",
            table(["module", "name", "value", "what it means"], rows),
            "",
            f"{len(found)} thresholds across {len({rule.module for rule in found})} modules.",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    """Write or check the thresholds document."""
    return run(DOCUMENT, body(), argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
