"""What the wheel has to contain, checked against the source tree.

Three things in this package are not Python and every one of them is load
bearing. The rolled shape catalogue is a CSV, and without it every structure
built from a catalogue shape fails at import with a file not found. The typing
marker is an empty file, and without it a downstream project running a type
checker sees this package as untyped and silently loses every annotation in it.
The console script is an entry point, and without it ``shearstud`` is a module
somebody has to remember to invoke with ``-m``.

None of the three is exercised by running from a checkout, which is how every
test in this repository runs, so all three break in the wheel and nowhere else.
The packaging job in CI installs the wheel and drives the console script, which
catches them; this catches them a good deal earlier and says which one it is.
"""

from __future__ import annotations

import sys
import tomllib
from typing import Final

from shearstud.tools.walk import PACKAGE_ROOT, REPO_ROOT, report, source_files

#: Files inside the package that are not Python and have to ship anyway.
REQUIRED_FILES: Final[dict[str, str]] = {
    "py.typed": (
        "without it a downstream type checker sees this package as untyped "
        "and every annotation in it is lost"
    ),
    "data/rolled_shapes.csv": (
        "without it every structure built from a catalogue shape fails at "
        "import with a file not found"
    ),
}

#: The console script the package installs, and what it points at.
SCRIPT_NAME: Final[str] = "shearstud"
SCRIPT_TARGET: Final[str] = "shearstud.cli:run"


def config() -> dict[str, object]:
    """The packaging metadata."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        loaded: dict[str, object] = tomllib.load(handle)
    return loaded


def declared_packages() -> list[str]:
    """The directories the wheel is told to include."""
    build = config().get("tool", {})
    if not isinstance(build, dict):
        return []
    hatch = build.get("hatch", {})
    if not isinstance(hatch, dict):
        return []
    targets = hatch.get("build", {}).get("targets", {}).get("wheel", {})
    if not isinstance(targets, dict):
        return []
    listed = targets.get("packages", [])
    return [str(entry) for entry in listed] if isinstance(listed, list) else []


def subpackages() -> list[str]:
    """Every subpackage in the source tree, by name."""
    return sorted(
        path.name
        for path in PACKAGE_ROOT.iterdir()
        if path.is_dir() and (path / "__init__.py").exists()
    )


def scripts() -> dict[str, str]:
    """The console scripts the package declares."""
    project = config().get("project", {})
    if not isinstance(project, dict):
        return {}
    listed = project.get("scripts", {})
    return {str(k): str(v) for k, v in listed.items()} if isinstance(listed, dict) else {}


def problems() -> list[str]:
    """Everything the wheel needs and the source tree does not have."""
    found: list[str] = []
    for relative, why in REQUIRED_FILES.items():
        if not (PACKAGE_ROOT / relative).exists():
            found.append(f"the package has no {relative}: {why}")

    listed = declared_packages()
    if not listed:
        found.append("the wheel is not told which packages to include")
    for entry in listed:
        if not (REPO_ROOT / entry).exists():
            found.append(f"the wheel is told to include {entry}, which is not there")

    declared = scripts()
    if SCRIPT_NAME not in declared:
        found.append(f"the package declares no {SCRIPT_NAME!r} console script")
    elif declared[SCRIPT_NAME] != SCRIPT_TARGET:
        found.append(
            f"the {SCRIPT_NAME!r} script points at {declared[SCRIPT_NAME]!r} "
            f"and not at {SCRIPT_TARGET!r}"
        )

    for source in source_files(include_tools=True):
        try:
            source.path.relative_to(PACKAGE_ROOT)
        except ValueError:  # pragma: no cover - the walker only yields these
            found.append(f"{source.name} is outside the package the wheel ships")
    return found


def contents() -> list[str]:
    """What the wheel would carry, for a reader who wants to see it."""
    out = [f"{len(subpackages())} subpackages: {', '.join(subpackages())}"]
    out.extend(f"{name}: present" for name in REQUIRED_FILES)
    out.extend(f"script {name} -> {target}" for name, target in scripts().items())
    return out


def main(argv: list[str] | None = None) -> int:
    """Run the check and report."""
    args = sys.argv[1:] if argv is None else argv
    if "--list" in args:
        for line in contents():
            print(f"check_package: {line}")
    return report("check_package", problems())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
