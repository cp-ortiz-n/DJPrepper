#!/usr/bin/env python3
"""Measure bounded repository concurrency against an isolated temporary catalog."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audioextender.repositories.concurrency_probe import ConcurrencyProbeConfig, RepositoryConcurrencyProbe


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=50, help="Workload rounds, from 1 to 1000")
    parser.add_argument("--workers", type=int, default=6, help="Concurrent workers, from 1 to 16")
    parser.add_argument("--suspected-wait-ms", type=float, default=100.0)
    parser.add_argument("--output", type=Path, default=Path("output/reports/repository_concurrency.json"))
    return parser.parse_args()


def main() -> int:
    options = arguments()
    config = ConcurrencyProbeConfig(options.iterations, options.workers, options.suspected_wait_ms)
    with tempfile.TemporaryDirectory(prefix="audioextender-concurrency-") as temporary:
        report = RepositoryConcurrencyProbe(Path(temporary), config).run()
    report["generated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    options.output.parent.mkdir(parents=True, exist_ok=True)
    pending = options.output.with_suffix(".pending.json")
    pending.write_text(json.dumps(report, indent=2), encoding="utf-8")
    pending.replace(options.output)
    summary = report["summary"]
    print(
        f"Repository concurrency: {report['status'].upper()} · {summary['operations']} operations · "
        f"{summary['errors']} errors · {summary['stale_results']} stale results · "
        f"{summary['suspected_lock_waits']} suspected waits · report {options.output}"
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
