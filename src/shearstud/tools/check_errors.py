"""Errors are the package's own, they carry a message, and nothing is swallowed.

Four rules:

* **every raise is a package error.** A ``ValueError`` from inside this package
  is a bug escaping, not a condition, and a caller who writes
  ``except ShearstudError`` should catch everything this package means to say;
* **every raise carries a message.** ``raise InputError()`` is a traceback with
  nothing in it;
* **nothing is caught bare.** ``except:`` and ``except Exception:`` without a
  re-raise take the keyboard interrupt with them;
* **every caught error is used, or the handler is a fallback.** A caught error
  that is neither re-raised, nor chained with ``from``, nor named in the new
  message has lost the only information about what actually went wrong. The one
  exception is a fallback handler: a specific exception type and a short body
  that takes the other path and nothing else. ``except ValueError: return None``
  on a parse function is not swallowing anything, because the fact that it
  failed *is* the whole answer.

The third rule allows a bare ``except Exception`` that re-raises, because that
is how the transaction rollback is written and it does not swallow anything.
"""

from __future__ import annotations

import ast
import sys
from typing import Final

from shearstud.tools.walk import SourceFile, report, source_files

#: Exceptions a module may raise that are not this package's own.
ALLOWED_FOREIGN: Final[frozenset[str]] = frozenset({"NotImplementedError", "AssertionError"})

#: The root every package error descends from.
PACKAGE_ROOT_ERROR: Final[str] = "ShearstudError"

#: Longest a fallback handler's body may be. Past this it is doing work, and
#: work that ignores what it caught wants explaining.
MAX_FALLBACK_STATEMENTS: Final[int] = 3


def _raised_name(node: ast.Raise) -> str | None:
    """Name of the exception a raise statement builds, if it builds one."""
    if node.exc is None:
        return None
    target = node.exc
    if isinstance(target, ast.Call):
        target = target.func
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _has_message(node: ast.Raise) -> bool:
    if not isinstance(node.exc, ast.Call):
        return False
    return bool(node.exc.args) or bool(node.exc.keywords)


def _package_errors() -> set[str]:
    """Every error class the package declares."""
    from shearstud import errors

    return {
        name
        for name in dir(errors)
        if isinstance(getattr(errors, name), type)
        and issubclass(getattr(errors, name), BaseException)
    }


def _reraises(handler: ast.ExceptHandler) -> bool:
    return any(isinstance(node, ast.Raise) for node in ast.walk(handler))


def _is_fallback(handler: ast.ExceptHandler) -> bool:
    """True when the handler just takes the other path.

    A specific exception type, a short body, no nested handling and no raise.
    The failure itself is the information, and there is nothing in the exception
    object worth carrying forward.
    """
    if handler.type is None:
        return False
    if len(handler.body) > MAX_FALLBACK_STATEMENTS:
        return False
    return all(not isinstance(node, ast.Raise | ast.Try) for node in ast.walk(handler))


def _uses_the_caught_error(handler: ast.ExceptHandler) -> bool:
    """True when the handler chains, re-raises or names what it caught."""
    if handler.name is None:
        return _reraises(handler)
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise) and node.cause is not None:
            return True
        if isinstance(node, ast.Name) and node.id == handler.name:
            return True
    return False


def problems() -> list[str]:
    """Foreign raises, empty raises, bare catches and swallowed errors."""
    known = _package_errors() | ALLOWED_FOREIGN
    found: list[str] = []
    for source in source_files(include_tools=True):
        for node in ast.walk(source.tree):
            if isinstance(node, ast.Raise):
                _check_raise(source, node, known, found)
            elif isinstance(node, ast.ExceptHandler):
                _check_handler(source, node, found)
    return found


def _check_raise(source: SourceFile, node: ast.Raise, known: set[str], problems: list[str]) -> None:
    name = _raised_name(node)
    if name is None:
        return
    if name not in known and not name.endswith("Error"):
        return
    if name not in known:
        problems.append(f"{source.name}:{node.lineno} raises {name}, which is not ours")
        return
    if name in ALLOWED_FOREIGN:
        return
    if not _has_message(node):
        problems.append(f"{source.name}:{node.lineno} raises {name} with no message")


def _check_handler(source: SourceFile, node: ast.ExceptHandler, problems: list[str]) -> None:
    if node.type is None:
        problems.append(f"{source.name}:{node.lineno} catches everything bare")
        return
    caught = node.type
    names = [caught] if not isinstance(caught, ast.Tuple) else list(caught.elts)
    is_broad = any(
        isinstance(n, ast.Name) and n.id in ("Exception", "BaseException") for n in names
    )
    if is_broad and not _reraises(node):
        problems.append(f"{source.name}:{node.lineno} catches Exception without re raising")
    if not _uses_the_caught_error(node) and not _is_fallback(node):
        problems.append(f"{source.name}:{node.lineno} catches an error and does not use it")


def error_names() -> list[str]:
    """Every error class the package declares, sorted."""
    return sorted(_package_errors())


def main() -> int:
    """Run the check and report."""
    if PACKAGE_ROOT_ERROR not in _package_errors():  # pragma: no cover - defensive
        return report("check_errors", [f"the package has no {PACKAGE_ROOT_ERROR}"])
    return report("check_errors", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
