"""The changelog says what the version is, so the version has to agree.

Three claims here have right answers in the code and are checked. The newest
entry names the version the package reports, the entries run newest first, and
each one carries a date that parses. Everything else about a changelog is
editorial and is left alone.

The version agreement is the one worth having. A release cut from a tree whose
changelog still tops out at the previous version produces a wheel nobody can
match to a set of changes, and the mismatch is invisible until somebody in
another office asks which version corrected the stud coefficient.

The last rule is about the sections rather than the version. A release that
changes an answer has to say so in the words the changelog reserves for it,
because a rating engineer reads this file to find out whether last year's
number would come out differently today, and a "Fixed" heading with no such
mark says the answer is unchanged.
"""

from __future__ import annotations

import re
import sys
import tomllib
from datetime import date
from itertools import pairwise
from typing import Final

from shearstud import __version__
from shearstud.tools.walk import REPO_ROOT, report

#: The file itself.
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

#: A release heading: ``## 0.4.0 - 2026-04-13``.
RELEASE = re.compile(r"^## (\d+\.\d+\.\d+) - (\d{4}-\d{2}-\d{2})$", re.MULTILINE)

#: Section headings a release may carry.
SECTIONS: Final[frozenset[str]] = frozenset({"Added", "Changed", "Fixed", "Removed"})

#: What an entry that changes a number has to say about itself.
RESULT_MARK: Final[str] = "**Changes results.**"

#: Sections where an unmarked entry is worth nothing to a rating engineer, so
#: at least one entry in them has to carry the mark.
MARKED_SECTIONS: Final[frozenset[str]] = frozenset({"Fixed"})


def releases() -> list[tuple[str, date]]:
    """Every release heading, in the order they appear."""
    if not CHANGELOG.exists():
        return []
    text = CHANGELOG.read_text(encoding="utf-8")
    return [(version, date.fromisoformat(when)) for version, when in RELEASE.findall(text)]


def declared_version() -> str:
    """The version the packaging metadata carries."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def sections_of(version: str) -> list[str]:
    """The section headings under one release."""
    text = CHANGELOG.read_text(encoding="utf-8")
    headings = list(RELEASE.finditer(text))
    for index, match in enumerate(headings):
        if match.group(1) != version:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        body = text[match.end() : end]
        return re.findall(r"^### (.+)$", body, flags=re.MULTILINE)
    return []


def body_of(version: str) -> str:
    """Everything written under one release."""
    text = CHANGELOG.read_text(encoding="utf-8")
    headings = list(RELEASE.finditer(text))
    for index, match in enumerate(headings):
        if match.group(1) != version:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        return text[match.end() : end]
    return ""


def problems() -> list[str]:
    """Everything the changelog says that the code does not."""
    if not CHANGELOG.exists():
        return [f"there is no {CHANGELOG.name}"]
    found: list[str] = []
    entries = releases()
    if not entries:
        return ["no release headings, expected '## <version> - <date>'"]

    newest, _ = entries[0]
    if newest != __version__:
        found.append(f"the newest entry is {newest} and the package reports {__version__}")
    declared = declared_version()
    if declared != __version__:
        found.append(f"pyproject says {declared} and the package reports {__version__}")

    for (version, when), (older, earlier) in pairwise(entries):
        if when < earlier:
            found.append(f"{version} is dated {when}, before {older} at {earlier}")

    seen: set[str] = set()
    for version, _ in entries:
        if version in seen:
            found.append(f"{version} has more than one entry")
        seen.add(version)

    for version, _ in entries:
        headings = sections_of(version)
        if not headings:
            found.append(f"{version} has no sections")
        for heading in headings:
            if heading not in SECTIONS:
                found.append(f"{version} has a {heading!r} section, expected one of {SECTIONS}")

    for version, _ in entries:
        marked = set(sections_of(version)) & MARKED_SECTIONS
        if marked and RESULT_MARK not in body_of(version):
            found.append(
                f"{version} fixes something and no entry says {RESULT_MARK}; "
                f"a fix that changes no number does not belong under Fixed"
            )
    return found


def main(argv: list[str] | None = None) -> int:
    """Run the check and report."""
    if argv is not None and "--list" in argv:
        for version, when in releases():
            print(f"check_changelog: {version} on {when}")
    return report("check_changelog", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
