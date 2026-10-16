.PHONY: help install quality coverage stability browser browser-install test-python test-js lint format-check type-check

help:
	@printf '%s\n' \
		'install          Install Python and JavaScript development dependencies' \
		'quality          Run the authoritative standard quality gate' \
		'coverage         Generate Python and JavaScript coverage reports' \
		'stability        Run persistence and workflow stability checks' \
		'browser          Run browser workflow and accessibility checks' \
		'browser-install  Install the pinned Chromium test browser' \
		'test-python      Run the complete Python test suite' \
		'test-js          Run JavaScript syntax and unit tests' \
		'lint             Run Python and JavaScript linters' \
		'format-check     Run Python and frontend formatting ratchets' \
		'type-check       Run Python type checking'

install:
	.venv/bin/python -m pip install -r requirements-dev.txt
	npm ci

quality:
	./scripts/check_quality.sh

coverage:
	./scripts/check_coverage.sh

stability:
	./scripts/run_stability_gate.sh

browser:
	npm run check:browser

browser-install:
	npm run check:browser:install

test-python:
	.venv/bin/python -m unittest discover -s tests -t .

test-js:
	npm run check

lint:
	.venv/bin/ruff check .
	npm run lint

format-check:
	.venv/bin/python scripts/check_python_format.py
	npm run format:check

type-check:
	.venv/bin/mypy

