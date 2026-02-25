"""The command reference, built by walking the command tree that ships.

Not by reading the source. A command registered from another module, or renamed
by its decorator, or shadowed by a later one with the same name, is in the built
tree and is what a user meets. A source scan would list what somebody wrote down
and miss all three.
"""

from __future__ import annotations

import sys

import click

from shearstud.tools.check_cli import _command_tree
from shearstud.tools.generated import Document, run, table

#: Where this document goes.
DOCUMENT = Document(filename="commands.md", command="build_commands")

#: The root group's own path in the tree. It is the program, not a command,
#: and listing it would put `shearstud` in the table of things to run.
ROOT_PATH = "main"


def _option_line(param: click.Option) -> list[str]:
    flags = ", ".join(f"`{opt}`" for opt in param.opts)
    default = "" if param.default in (None, False) else f"`{param.default}`"
    return [flags, default, (param.help or "").strip()]


def command_rows() -> list[list[str]]:
    """One row per command, in the order the tree walks."""
    rows = []
    for path, command in _command_tree():
        if path in ("", ROOT_PATH) or isinstance(command, click.Group):
            continue
        first = (command.help or "").strip().splitlines()
        rows.append([f"`{path.removeprefix('main ')}`", first[0] if first else ""])
    return sorted(rows)


def group_rows() -> list[list[str]]:
    """One row per group of commands."""
    rows = []
    for path, command in _command_tree():
        if path in ("", ROOT_PATH) or not isinstance(command, click.Group):
            continue
        first = (command.help or "").strip().splitlines()
        rows.append([f"`{path.removeprefix('main ')}`", first[0] if first else ""])
    return sorted(rows)


def option_sections() -> list[str]:
    """One section per command, listing its options."""
    out: list[str] = []
    for path, command in _command_tree():
        if path in ("", ROOT_PATH) or isinstance(command, click.Group):
            continue
        options = [
            _option_line(param)
            for param in command.params
            if isinstance(param, click.Option) and param.name not in ("help", "version")
        ]
        arguments = [
            f"`{param.name}`" for param in command.params if isinstance(param, click.Argument)
        ]
        name = path.removeprefix("main ")
        out.append(f"### `shearstud {name}`")
        out.append("")
        out.append((command.help or "").strip())
        out.append("")
        if arguments:
            out.append("Takes " + ", ".join(arguments) + ".")
            out.append("")
        if options:
            out.append(table(["Option", "Default", "What it does"], options))
            out.append("")
    return out


def body() -> str:
    """The whole document."""
    parts = [
        "# Commands",
        "",
        "Every command takes `--book` to say which book of record to work on. It",
        "defaults to `shearstud.sqlite3` in the working directory and is never read",
        "from the environment, because a rating office runs one book per district.",
        "",
        "## Groups",
        "",
        table(["Group", "What it covers"], group_rows()),
        "",
        "## Commands",
        "",
        table(["Command", "What it does"], command_rows()),
        "",
        "## Detail",
        "",
        *option_sections(),
    ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    """Write or check the command reference."""
    return run(DOCUMENT, body(), argv)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
