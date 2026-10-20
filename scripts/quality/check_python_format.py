"""Reject new Ruff-format debt while existing debt is cleaned separately."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).with_name("format_baseline.json")


def main() -> int:
    expected = set(json.loads(BASELINE.read_text(encoding="utf-8"))["python"])
    result = subprocess.run(
        [str(ROOT / ".venv" / "bin" / "ruff"), "format", "--check", "--output-format", "json", "."],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        return result.returncode or 1
    actual = {
        str(Path(item["filename"]).resolve().relative_to(ROOT)) for item in payload if item.get("code") == "unformatted"
    }
    regressions = sorted(actual - expected)
    resolved = sorted(expected - actual)
    if regressions:
        print("New Ruff formatting debt:")
        print("\n".join(f"  {path}" for path in regressions))
        return 1
    print(f"Python formatting ratchet passed ({len(actual)} known legacy files remain).")
    if resolved:
        print("Remove these now-formatted files from scripts/quality/format_baseline.json:")
        print("\n".join(f"  {path}" for path in resolved))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
