"""Stable repository paths for tests at any nesting depth."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"
