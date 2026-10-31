from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from audioextender.web.routes.job_media_routes import _generate_waveform


class SequentialAudio:
    def __init__(self) -> None:
        self.blocks = [
            np.asarray([[0.0], [0.5]], dtype=np.float32),
            np.asarray([[1.0], [0.5]], dtype=np.float32),
            np.asarray([], dtype=np.float32).reshape(0, 1),
        ]
        self.reads = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self, _frames: int, **_kwargs) -> np.ndarray:
        self.reads += 1
        return self.blocks.pop(0)


class JobMediaPerformanceTests(unittest.TestCase):
    def test_waveform_generation_uses_one_sequential_pass_and_returns_fixed_points(self) -> None:
        audio = SequentialAudio()
        info = SimpleNamespace(frames=4, duration=2.0)
        with (
            patch("audioextender.web.routes.job_media_routes.sf.info", return_value=info),
            patch("audioextender.web.routes.job_media_routes.sf.SoundFile", return_value=audio),
        ):
            duration, peaks = _generate_waveform(Path("track.wav"), 8)

        self.assertEqual(duration, 2.0)
        self.assertEqual(peaks.shape, (8,))
        self.assertTrue(np.isfinite(peaks).all())
        self.assertGreater(float(peaks.max()), 0)
        self.assertEqual(audio.reads, 3)


if __name__ == "__main__":
    unittest.main()
