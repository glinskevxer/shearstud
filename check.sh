#!/usr/bin/env bash
# Everything CI runs, in the order it runs it. One command, so that a change
# that would go red on a push goes red here first.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
PY="${PYTHON:-python}"
failed=()

run() {
  local name="$1"; shift
  printf '%-28s' "$name"
  if "$@" > /tmp/shearstud-check.log 2>&1; then
    echo "ok"
  else
    echo "FAILED"
    tail -30 /tmp/shearstud-check.log
    failed+=("$name")
  fi
}

run "ruff check"    "$PY" -m ruff check .
run "ruff format"   "$PY" -m ruff format --check .
run "mypy"          "$PY" -m mypy
for module in $(ls src/shearstud/tools/check_*.py | xargs -n1 basename | sed 's/\.py$//'); do
  run "$module" "$PY" -m "shearstud.tools.$module"
done
for module in build_architecture build_commands build_glossary build_lock schema_dump; do
  run "$module" "$PY" -m "shearstud.tools.$module" --check
done
run "pytest" "$PY" -m pytest -p no:cacheprovider -n auto "$@"
run "smoke"  "$PY" -m shearstud.tools.smoke --quiet

if [ "${#failed[@]}" -gt 0 ]; then
  printf '\n%d FAILED: %s\n' "${#failed[@]}" "${failed[*]}"
  exit 1
fi
echo
echo "all gates clean"
