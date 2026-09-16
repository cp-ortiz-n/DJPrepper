from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from helpers.progress import ProgressBar
from helpers.resource_planner import GIB, WorkloadEstimate, choose_worker_count


class ProgressTests(unittest.TestCase):
    @patch("helpers.progress.time.monotonic")
    def test_slow_work_is_reported_and_progress_never_moves_backward(self, clock) -> None:
        clock.return_value = 100.0
        progress = ProgressBar(song="Song.mp3", use_stems=True)
        with redirect_stdout(StringIO()):
            progress.update(50, "Analyzing")
            progress.update(20, "Older event")
        self.assertEqual(progress.percent, 50.0)
        clock.return_value = 116.0
        self.assertIn("still active 00:16", progress._lines()[1])

    @patch("helpers.progress.time.monotonic")
    def test_demucs_line_identifies_mps(self, clock) -> None:
        clock.return_value = 100.0
        progress = ProgressBar(song="Song.mp3", use_stems=True)
        with redirect_stdout(StringIO()):
            progress.update(75, "Demucs MPS separation 42%")
        line = progress._lines()[1]
        self.assertIn("Stems", line)
        self.assertIn("Apple GPU (MPS)", line)
        self.assertIn("42%", line)


class ResourcePlannerTests(unittest.TestCase):
    @patch("helpers.resource_planner._physical_memory", return_value=16 * GIB)
    @patch("helpers.resource_planner.estimate_track")
    def test_auto_workers_respect_memory_budget(self, estimate, _memory) -> None:
        estimate.side_effect = lambda path: WorkloadEstimate(path, 180.0, 3 * GIB)
        paths = [Path(f"song-{index}.wav") for index in range(4)]
        workers, _, memory = choose_worker_count(paths, "auto", False)
        self.assertEqual(workers, 2)
        self.assertEqual(memory, 16 * GIB)

    @patch("helpers.resource_planner._physical_memory", return_value=16 * GIB)
    @patch("helpers.resource_planner.estimate_track")
    def test_demucs_auto_mode_uses_one_worker(self, estimate, _memory) -> None:
        estimate.side_effect = lambda path: WorkloadEstimate(path, 180.0, GIB)
        workers, _, _ = choose_worker_count([Path("a.wav"), Path("b.wav")], "auto", True)
        self.assertEqual(workers, 1)


if __name__ == "__main__":
    unittest.main()
