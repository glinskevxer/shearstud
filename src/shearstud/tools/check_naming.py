"""Names say what the thing is, in the words this domain already uses.

Three rules, and each of them is here because the alternative produced a real
misunderstanding on this project:

* **no vague names.** ``data``, ``info``, ``result``, ``obj`` and their friends
  are banned as whole names. They are not wrong, they are empty, and a function
  taking ``data`` gives a reader nothing to check the call site against;
* **no abbreviations the domain does not use.** ``sect`` is not a section and
  ``dl`` is not a dead load anywhere but in a variable somebody was tired of
  typing. The domain's own abbreviations, ``adtt`` and ``rf`` and the unit
  suffixes, are exactly the ones a bridge engineer would read out loud;
* **a stored boolean reads as a question.** ``is_``, ``has_``, ``needs_``,
  ``can_`` and ``was_`` all do; a bare adjective on a field does not, and
  ``compact = True`` beside ``compact = section`` is a bug waiting.

The boolean rule applies to fields and to positional parameters, not to keyword
only flags. ``compose(section, deck, creep=True)`` names the flag at the call
site, which is the whole reason those parameters are keyword only, and forcing
them to ``is_creeping`` would make every call read worse. Command line handlers
are exempt as well, because click names their parameters from the option.

The vague list is a list, not a heuristic. A heuristic that flagged short names
would flag ``fy_ksi``, and a heuristic that flagged nouns would flag everything.
"""

from __future__ import annotations

import ast
import sys
from typing import Final

from shearstud.tools.walk import SourceFile, report, source_files

#: Whole names that say nothing.
VAGUE: Final[frozenset[str]] = frozenset(
    {
        "data",
        "info",
        "obj",
        "item",
        "items",
        "thing",
        "things",
        "temp",
        "tmp",
        "val",
        "vals",
        "res",
        "ret",
        "arg",
        "args_",
        "input",
        "output",
        "stuff",
        "misc",
        "helper",
        "manager",
        "handler",
        "processor",
        "util",
        "utils",
    }
)

#: Abbreviations this domain does not use, and what it says instead.
BANNED_ABBREVIATIONS: Final[dict[str, str]] = {
    "sect": "section",
    "gird": "girder",
    "dl": "dead_load",
    "ll": "live_load",
    "mom": "moment",
    "shr": "shear",
    "len": "length",
    "num": "count",
    "idx": "index",
    "cnt": "count",
    "cfg": "settings",
    "params": "settings",
}

#: Prefixes that make a name read as a question.
BOOLEAN_PREFIXES: Final[tuple[str, ...]] = ("is_", "has_", "needs_", "can_", "was_", "should_")

#: Domain adjectives that read as a condition without a prefix. Every one of
#: these is a word a bridge engineer says about a structure, not a programmer's
#: flag, and ``infinite_life`` is what the specification calls it.
DOMAIN_ADJECTIVES: Final[frozenset[str]] = frozenset(
    {"continuous", "infinite_life", "reversed_travel"}
)

#: Layers whose parameter names are not chosen by this package.
EXTERNALLY_NAMED: Final[frozenset[str]] = frozenset({"cli"})


def _is_bool(annotation: ast.expr | None) -> bool:
    return isinstance(annotation, ast.Name) and annotation.id == "bool"


def _reads_as_a_question(name: str) -> bool:
    return name.startswith(BOOLEAN_PREFIXES)


def _check_name(source: SourceFile, name: str, line: int, what: str, problems: list[str]) -> None:
    bare = name.lstrip("_")
    if bare in VAGUE:
        problems.append(f"{source.name}:{line} {what} {name!r} says nothing")
    if bare in BANNED_ABBREVIATIONS:
        instead = BANNED_ABBREVIATIONS[bare]
        problems.append(f"{source.name}:{line} {what} {name!r} should be {instead!r}")


def problems() -> list[str]:
    """Every name that is vague, abbreviated or a boolean that does not ask."""
    found: list[str] = []
    for source in source_files():
        for node in ast.walk(source.tree):
            if isinstance(node, ast.FunctionDef):
                _check_name(source, node.name, node.lineno, "function", found)
                args = node.args
                for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
                    _check_name(source, arg.arg, node.lineno, "parameter", found)
                positional = [*args.posonlyargs, *args.args]
                if source.layer in EXTERNALLY_NAMED:
                    continue
                for arg in positional:
                    if _is_bool(arg.annotation) and not _reads_as_a_question(arg.arg):
                        found.append(
                            f"{source.name}:{node.lineno} boolean parameter {arg.arg!r} "
                            f"does not read as a question"
                        )
            elif isinstance(node, ast.ClassDef):
                _check_name(source, node.name, node.lineno, "class", found)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
                _check_name(source, name, node.lineno, "field", found)
                bare = name.lstrip("_")
                if (
                    _is_bool(node.annotation)
                    and not _reads_as_a_question(name)
                    and bare not in DOMAIN_ADJECTIVES
                ):
                    found.append(
                        f"{source.name}:{node.lineno} boolean field {name!r} "
                        f"does not read as a question"
                    )
    return found


def main() -> int:
    """Run the check and report."""
    return report("check_naming", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
