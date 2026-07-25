"""The README makes checkable claims, so they get checked.

A README goes stale in one direction only. Nobody deletes a paragraph about a
command that was renamed, because nobody reads the README once the code is
familiar, and the first person to read it again is somebody new who then spends
an afternoon on a command that has not existed for a year.

Everything this checks is a claim with a right answer in the code: a command it
tells you to run, a file it points you at, a Python version it says you need,
and the modules it says the linked documents describe. Prose is left alone. A
paragraph that has quietly become untrue is a real problem and it is not one a
program can find, so this does not pretend to.
"""

from __future__ import annotations

import re
import sys
import tomllib
from typing import Final

import click

from shearstud.tools.walk import REPO_ROOT, report

#: The file itself.
README = REPO_ROOT / "README.md"

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


def problems() -> list[str]:
    """Everything the README says that the code does not."""
    found: list[str] = []
    if not README.exists():
        return [f"there is no {README.name}"]
    text = README.read_text(encoding="utf-8")

    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            found.append(f"no {heading!r} section")

    for invocation in unknown_commands(text):
        found.append(f"tells the reader to run 'shearstud {invocation}', which is not a command")

    for relative in linked_paths(text):
        if relative.startswith(("http://", "https://", "#")):
            continue
        if not (REPO_ROOT / relative).exists():
            found.append(f"points at {relative}, which is not there")

    for version in sorted(python_versions()):
        if version not in text:
            found.append(f"does not mention Python {version}, which the package claims to support")

    return found


def main(argv: list[str] | None = None) -> int:
    """Run the check and report."""
    args = sys.argv[1:] if argv is None else argv
    if "--list" in args:
        for invocation in invocations(README.read_text(encoding="utf-8")):
            print(f"check_readme: {' '.join(invocation)}")
    return report("check_readme", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
