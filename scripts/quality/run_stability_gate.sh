#!/bin/sh
set -eu

cd "$(dirname "$0")/../.."
exec .venv/bin/python -m unittest -v tests.integration.test_stability_workflow
