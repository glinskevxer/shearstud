"""The hand written documents make checkable claims, so they get checked.

Documentation goes stale in one direction only. Nobody deletes a paragraph
about a command that was renamed, because nobody reads the documents once the
code is familiar, and the first person to read them again is somebody new who
then spends an afternoon on a command that has not existed for a year.

Everything this checks is a claim with a right answer in the code: a command a
document tells you to run, a file it points you at, and a Python version it
says you need. Prose is left alone. A paragraph that has quietly become untrue
is a real problem and it is not one a program can find, so this does not
pretend to.

The generated documents are not checked here. They are rebuilt from the code
by their own commands and compared in CI, which is a stronger guarantee than
anything this could offer, and reading them here would report the same drift
twice under two names.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from typing import Final

import click

from shearstud.tools.walk import REPO_ROOT, report

#: The README, which carries the required headings.
README = REPO_ROOT / "README.md"

#: The hand written documents under ``docs``. Everything else there is
#: generated and is checked by the command that generates it.
HANDWRITTEN: Final[tuple[str, ...]] = ("workflow.md",)

#: Headings the README has to carry. Not a style rule: each of these is a
#: question somebody arriving at the repository asks in their first ten
#: minutes, and a README that answers none of them wastes the afternoon it was
#: written to save.
REQUIRED_HEADINGS: Final[tuple[str, ...]] = (
    "## Installing",
    "## Getting started",
    "## The book of record",
    "## Checking the repository",
)

#: Command lines in the README start with this.
INVOCATION: Final[str] = "shearstud "

#: Words after ``shearstud`` that are options or arguments rather than command
#: names. Anything starting with a dash is obvious; these are not.
NOT_A_COMMAND: Final[frozenset[str]] = frozenset({"--help", "--version"})


def _fenced_blocks(text: str) -> list[str]:
    """Every fenced code block in the document."""
    return re.findall(r"```[a-z]*\n(.*?)```", text, flags=re.DOTALL)


def invocations(text: str) -> list[list[str]]:
    """Every ``shearstud`` command line the README tells a reader to run."""
    out: list[list[str]] = []
    for block in _fenced_blocks(text):
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped.startswith(INVOCATION):
                continue
            out.append(stripped.split()[1:])
    return out


def resolve(words: list[str]) -> tuple[list[str], str | None]:
    """The command names in an invocation, and the first word that is not one.

    Options are stepped over, and ``--book`` takes a value so two words are
    stepped over there. The walk stops as soon as it reaches a leaf command,
    because everything after one is an argument: ``rate 18-SH-0473`` must not
    read the structure number as a missing subcommand. A word that is not a
    command while the walk is still standing on a group is the failure this
    exists to find.
    """
    from shearstud.cli import main as cli_main

    out: list[str] = []
    node: click.Command = cli_main
    index = 0
    while index < len(words):
        word = words[index]
        if word.startswith("-"):
            index += 2 if word == "--book" else 1
            continue
        if not isinstance(node, click.Group):
            return out, None
        child = node.commands.get(word)
        if child is None:
            return out, word
        out.append(word)
        node = child
        index += 1
    return out, None


def command_path(words: list[str]) -> list[str]:
    """Just the command names in an invocation."""
    return resolve(words)[0]


def unknown_commands(text: str) -> list[str]:
    """Command lines in the README that do not resolve to a real command."""
    out: list[str] = []
    for words in invocations(text):
        found, missing = resolve(words)
        if missing is not None:
            out.append(" ".join(words))
            continue
        if not found and not set(words) & NOT_A_COMMAND:
            out.append(" ".join(words))
    return out


def linked_paths(text: str) -> list[str]:
    """Every repository path the README links to or names in backticks."""
    linked = re.findall(r"\]\(([^)]+)\)", text)
    quoted = re.findall(r"`([a-zA-Z0-9_./-]+\.(?:md|txt|lock|json|toml|sh))`", text)
    return sorted({*linked, *quoted})


def python_versions() -> set[str]:
    """The Python versions the package says it supports."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        config = tomllib.load(handle)
    classifiers = config["project"].get("classifiers", [])
    prefix = "Programming Language :: Python :: "
    return {line[len(prefix) :] for line in classifiers if line.startswith(prefix)}


def documents() -> list[Path]:
    """Every hand written document, the README first."""
    out = [README] if README.exists() else []
    out.extend(
        path for path in (REPO_ROOT / "docs" / name for name in HANDWRITTEN) if path.exists()
    )
    return out


def problems() -> list[str]:
    """Everything the hand written documents say that the code does not."""
    found: list[str] = []
    if not README.exists():
        return [f"there is no {README.name}"]

    readme = README.read_text(encoding="utf-8")
    for heading in REQUIRED_HEADINGS:
        if heading not in readme:
            found.append(f"{README.name} has no {heading!r} section")
    for version in sorted(python_versions()):
        if version not in readme:
            found.append(
                f"{README.name} does not mention Python {version}, "
                f"which the package claims to support"
            )

    for path in documents():
        found.extend(_check_document(path))
    return found


def _check_document(path: Path) -> list[str]:
    """The claims one document makes that have a right answer in the code."""
    found: list[str] = []
    text = path.read_text(encoding="utf-8")
    for invocation in unknown_commands(text):
        found.append(
            f"{path.name} tells the reader to run 'shearstud {invocation}', which is not a command"
        )
    for relative in linked_paths(text):
        if relative.startswith(("http://", "https://", "#")):
            continue
        if not (REPO_ROOT / relative).exists():
            found.append(f"{path.name} points at {relative}, which is not there")
    return found


def main(argv: list[str] | None = None) -> int:
    """Run the check and report."""
    args = sys.argv[1:] if argv is None else argv
    if "--list" in args:
        for path in documents():
            for invocation in invocations(path.read_text(encoding="utf-8")):
                print(f"check_docs: {path.name}: {' '.join(invocation)}")
    return report("check_docs", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
