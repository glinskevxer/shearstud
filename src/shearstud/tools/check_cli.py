"""The command line documents itself: every command and every option has help.

A command with no help line is invisible in ``--help``, and an option with no
help is a flag a user has to read the source to understand. Both are checked by
walking the built command tree rather than the source, because that is what a
user actually meets: a command registered from another module, or shadowed by a
name collision, shows up here and does not show up in a source scan.

The destructive commands are checked too. Anything that deletes has to offer a
way to say yes without a prompt, because the alternative is a script that hangs
waiting for an answer nobody is there to give.
"""

from __future__ import annotations

import sys
from typing import Final

import click

from shearstud.tools.walk import report

#: Commands that remove something and therefore need a confirmation flag.
DESTRUCTIVE: Final[frozenset[str]] = frozenset({"delete", "prune"})

#: What a confirmation flag may be called.
CONFIRM_FLAGS: Final[frozenset[str]] = frozenset({"yes", "force"})

#: Shortest help line that says anything.
MIN_HELP_CHARS: Final[int] = 12


def _command_tree() -> list[tuple[str, click.Command]]:
    """Every command in the group, with its dotted path."""
    from shearstud.cli import main

    out: list[tuple[str, click.Command]] = []

    def walk(prefix: str, command: click.Command) -> None:
        name = f"{prefix} {command.name}".strip()
        out.append((name, command))
        if isinstance(command, click.Group):
            for child in command.commands.values():
                walk(name, child)

    walk("", main)
    return out


def _option_names(command: click.Command) -> list[str]:
    return [param.name or "" for param in command.params if isinstance(param, click.Option)]


def problems() -> list[str]:
    """Commands and options with no help, and deletes with no way to say yes."""
    found: list[str] = []
    for path, command in _command_tree():
        help_text = (command.help or "").strip()
        if not help_text:
            found.append(f"{path} has no help")
        elif len(help_text) < MIN_HELP_CHARS:
            found.append(f"{path} has help too short to say anything")
        for param in command.params:
            if not isinstance(param, click.Option):
                continue
            if param.name in ("help", "version"):
                continue
            if not (param.help or "").strip():
                found.append(f"{path} option --{param.name} has no help")
        leaf = path.rsplit(" ", 1)[-1]
        offers_a_flag = bool(CONFIRM_FLAGS & set(_option_names(command)))
        if leaf in DESTRUCTIVE and not offers_a_flag:
            found.append(f"{path} deletes and offers no way to say yes without a prompt")
    return found


def command_paths() -> list[str]:
    """Every command path, sorted, for the generated command list."""
    return sorted(path for path, _ in _command_tree() if path)


def command_help() -> dict[str, str]:
    """Command path to its first help line, for the generated command list."""
    out: dict[str, str] = {}
    for path, command in _command_tree():
        if not path:
            continue
        first = (command.help or "").strip().splitlines()
        out[path] = first[0] if first else ""
    return out


def main() -> int:
    """Run the check and report."""
    return report("check_cli", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
