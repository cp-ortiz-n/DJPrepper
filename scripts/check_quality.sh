#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

run() {
  printf '\n==> %s\n' "$1"
  shift
  "$@"
}

run "Python lint" .venv/bin/ruff check .
run "Python formatting ratchet" .venv/bin/python scripts/check_python_format.py
run "Python type checking" .venv/bin/mypy
run "Python tests and architecture safeguards" .venv/bin/python -m unittest discover -s tests
run "JavaScript lint, formatting, syntax, and tests" npm run quality

printf '\nStandard quality gate passed.\n'
