#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

node_major=$(node -p "process.versions.node.split('.')[0]")
if [ "$node_major" -lt 20 ]; then
  printf 'JavaScript coverage requires Node 20 or newer (found %s). Run `nvm use 22` and retry.\n' "$(node --version)" >&2
  exit 1
fi

printf '\n==> Python coverage\n'
.venv/bin/python -m coverage erase
.venv/bin/python -m coverage run -m unittest discover -s tests -t .
.venv/bin/python -m coverage report -m
.venv/bin/python -m coverage json
.venv/bin/python -m coverage lcov -o coverage/lcov-python.info

printf '\n==> JavaScript coverage\n'
npm run coverage:js

printf '\nCoverage reports refreshed in coverage/.\n'
