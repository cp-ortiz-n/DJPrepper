from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from audioextender.repositories.concurrency_probe import ConcurrencyProbeConfig, RepositoryConcurrencyProbe


class RepositoryConcurrencyProbeTests(unittest.TestCase):
    def test_bounded_concurrent_workload_preserves_committed_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = RepositoryConcurrencyProbe(
                Path(temporary), ConcurrencyProbeConfig(iterations=8, workers=4, suspected_wait_ms=1000)
            ).run()

        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["disposable"])
        self.assertEqual(report["summary"]["operations"], 32)
        self.assertEqual(report["summary"]["final_jobs"], 8)
        self.assertEqual(report["summary"]["final_tracks"], 8)
        self.assertEqual(report["summary"]["errors"], 0)
        self.assertEqual(report["summary"]["sqlite_locked_errors"], 0)
        self.assertEqual(report["summary"]["stale_results"], 0)
        self.assertEqual(report["recommended_follow_up"], "")
        self.assertEqual(set(report["latency_ms"]), {"catalog-read", "catalog-write", "job-write", "state-write"})

    def test_configuration_enforces_safety_limits(self) -> None:
        for values in (
            {"iterations": 0},
            {"iterations": 1001},
            {"workers": 0},
            {"workers": 17},
            {"suspected_wait_ms": 0},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ConcurrencyProbeConfig(**values)


if __name__ == "__main__":
    unittest.main()
