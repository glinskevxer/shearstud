"""Every value in this package is frozen, and this is what says so.

Nothing here is a container somebody mutates. A section, a rating, an influence
line, a strain record: each of them is a fact about a bridge at a moment, and a
fact that can be edited in place is a fact two callers can disagree about. Every
transformation returns a new object and says in its name what it did, which is
what lets a conditioned record be compared against the one that came off the
logger.

The rule is therefore that every dataclass in the application layers is frozen
and has slots. Frozen is the part that matters; slots is worth having with it
because a frozen class with slots refuses an attribute that was never declared,
which catches the typo that would otherwise create a second field nobody reads.

There is one exception in the repository and it is in the tools rather than the
application, so this does not reach it: the source file walker uses
``cached_property``, which stores into the instance dictionary, and there is no
dictionary under slots. That exception is written down where it lives.
"""

from __future__ import annotations

import ast
import sys
from typing import Final

from shearstud.tools.walk import SourceFile, public_classes, report, source_files

#: The decorator that makes a class a dataclass.
DECORATOR: Final[str] = "dataclass"

#: What every dataclass in the application layers has to pass.
REQUIRED: Final[tuple[str, ...]] = ("frozen", "slots")


def _decorator_of(node: ast.ClassDef) -> ast.Call | None:
    """The ``@dataclass(...)`` call on a class, if it carries one."""
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call):
            func = decorator.func
            if isinstance(func, ast.Name) and func.id == DECORATOR:
                return decorator
            if isinstance(func, ast.Attribute) and func.attr == DECORATOR:
                return decorator
    return None


def is_bare_dataclass(node: ast.ClassDef) -> bool:
    """Whether a class is decorated with ``@dataclass`` and no arguments.

    A bare decorator is a mutable dataclass, which is exactly what this rule
    is about, so it is reported rather than skipped.
    """
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == DECORATOR:
            return True
        if isinstance(decorator, ast.Attribute) and decorator.attr == DECORATOR:
            return True
    return False


def keywords_of(node: ast.ClassDef) -> dict[str, bool]:
    """The boolean arguments a dataclass decorator was given."""
    call = _decorator_of(node)
    if call is None:
        return {}
    out: dict[str, bool] = {}
    for keyword in call.keywords:
        if keyword.arg is None:
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, bool):
            out[keyword.arg] = keyword.value.value
    return out


def dataclasses_in(source: SourceFile) -> list[ast.ClassDef]:
    """Every public dataclass declared at the top level of a file."""
    return [
        node
        for node in public_classes(source)
        if is_bare_dataclass(node) or _decorator_of(node) is not None
    ]


def problems() -> list[str]:
    """Every dataclass that is not frozen, or has no slots."""
    found: list[str] = []
    for source in source_files():
        for node in dataclasses_in(source):
            given = keywords_of(node)
            for wanted in REQUIRED:
                if not given.get(wanted, False):
                    found.append(
                        f"{source.name}:{node.lineno} {node.name} is a dataclass "
                        f"without {wanted}=True"
                    )
    return found


def counts() -> dict[str, int]:
    """How many dataclasses each layer declares."""
    out: dict[str, int] = {}
    for source in source_files():
        found = dataclasses_in(source)
        if found:
            out[source.layer] = out.get(source.layer, 0) + len(found)
    return out


def main(argv: list[str] | None = None) -> int:
    """Run the check and report."""
    args = sys.argv[1:] if argv is None else argv
    if "--counts" in args:
        for layer, count in sorted(counts().items()):
            print(f"check_dataclasses: {layer or '(top level)'} declares {count}")
    return report("check_dataclasses", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
