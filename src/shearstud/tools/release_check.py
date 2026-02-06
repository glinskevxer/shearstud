"""Every gate, in one command, so that nothing is checked only by CI.

The gates are discovered rather than listed. ``check_*`` modules in this package
are found by import and every one of them is run, so a check added and not
wired up here fails this command's own self test rather than sitting unrun.
That is the failure this module exists to prevent: a check nobody runs is worse
than no check, because the repository looks like it is enforced.

The generated documents are run in ``--check`` form: they must already be
current in the working tree. Regenerating them here would put the regeneration
outside the diff, which is the same mistake as a check that repairs.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from dataclasses import dataclass
from typing import Final

from shearstud.tools import smoke
from shearstud.tools.walk import PACKAGE_ROOT, source_files, suite_files

#: Prefix a self check module carries.
CHECK_PREFIX: Final[str] = "check_"

#: Prefix a generated document builder carries. ``schema_dump`` is one too and
#: does not fit the pattern, so it is named.
BUILD_PREFIX: Final[str] = "build_"
EXTRA_BUILDERS: Final[tuple[str, ...]] = ("schema_dump",)


@dataclass(frozen=True, slots=True)
class GateResult:
    """What one gate did."""

    name: str
    code: int

    @property
    def passed(self) -> bool:
        """True when the gate came back clean."""
        return self.code == 0


def check_modules() -> list[str]:
    """Every self check module in the tools package, sorted."""
    return sorted(
        module.name
        for module in pkgutil.iter_modules([str(PACKAGE_ROOT / "tools")])
        if module.name.startswith(CHECK_PREFIX)
    )


def builder_modules() -> list[str]:
    """Every generated document builder, sorted."""
    found = {
        module.name
        for module in pkgutil.iter_modules([str(PACKAGE_ROOT / "tools")])
        if module.name.startswith(BUILD_PREFIX)
    }
    return sorted(found | set(EXTRA_BUILDERS))


def _run_module(name: str, argv: list[str] | None = None) -> int:
    module = importlib.import_module(f"shearstud.tools.{name}")
    entry = module.main
    if argv is None:
        return int(entry())
    return int(entry(argv))


def gates() -> list[GateResult]:
    """Run every check and every generated document, and report each."""
    out: list[GateResult] = []
    for name in check_modules():
        out.append(GateResult(name=name, code=_run_module(name)))
    for name in builder_modules():
        out.append(GateResult(name=name, code=_run_module(name, ["--check"])))
    out.append(GateResult(name="smoke", code=smoke.main(["--quiet"])))
    return out


def counts() -> dict[str, int]:
    """The numbers a release note quotes."""
    sources = source_files(include_tools=True)
    suite = suite_files()
    return {
        "modules": len(sources),
        "source_lines": sum(len(source.lines()) for source in sources),
        "test_files": len(suite),
        "test_lines": sum(len(source.lines()) for source in suite),
        "gates": len(check_modules()) + len(builder_modules()) + 1,
    }


def main(argv: list[str] | None = None) -> int:
    """Run every gate and report which failed."""
    args = sys.argv[1:] if argv is None else argv
    results = gates()
    failed = [result for result in results if not result.passed]
    if "--quiet" not in args:
        numbers = counts()
        print(
            f"release_check: {numbers['modules']} modules, "
            f"{numbers['source_lines']} source lines, "
            f"{numbers['test_files']} test files, {numbers['gates']} gates"
        )
    for result in failed:
        print(f"release_check: FAILED {result.name}")
    if failed:
        print(f"release_check: {len(failed)} of {len(results)} gates failed")
        return 1
    print(f"release_check: {len(results)} gates clean")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
