"""Small end-to-end test using generated audio rather than copyrighted music."""

from __future__ import annotations

import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np
import soundfile as sf

from audioextender.core.config import EditConfig
from audioextender.core.interfaces import NullProgressReporter
from audioextender.processing.track_processor import TrackProcessor


class SyntheticPipelineIntegrationTests(unittest.TestCase):
    def test_stereo_metronome_reaches_wav_export(self) -> None:
        sample_rate = 22050
        duration = 24.0
        frames = int(sample_rate * duration)
        time = np.arange(frames) / sample_rate
        mono = 0.05 * np.sin(2 * np.pi * 110.0 * time)
        # A stable 120 BPM kick-like pulse gives analysis an unambiguous grid.
        for beat_time in np.arange(0.5, duration, 0.5):
            start = int(beat_time * sample_rate)
            length = min(int(0.08 * sample_rate), frames - start)
            envelope = np.exp(-np.linspace(0, 8, length))
            mono[start:start + length] += 0.8 * envelope * np.sin(
                2 * np.pi * 60.0 * np.arange(length) / sample_rate
            )
        stereo = np.column_stack((mono, mono)).astype(np.float32)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "synthetic.wav"
            output = root / "synthetic (Extended Edit).wav"
            sf.write(source, stereo, sample_rate, subtype="PCM_16")
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore", message="Trying to estimate tuning from empty frequency set"
                )
                result = TrackProcessor().process(
                    source,
                    output,
                    EditConfig(
                        intro_bars=2,
                        outro_bars=0,
                        intro_bars_locked=True,
                        outro_bars_locked=True,
                        use_stems=False,
                        cache_directory=str(root / "cache"),
                        export_cues=False,
                        minimum_loop_quality=0.0,
                    ),
                    NullProgressReporter(),
                )
            exported, exported_rate = sf.read(output, always_2d=True)

        self.assertTrue(result.full_exported)
        self.assertGreater(result.beats, 20)
        self.assertEqual(exported_rate, sample_rate)
        self.assertEqual(exported.shape[1], 2)
        self.assertGreater(len(exported), len(stereo))


if __name__ == "__main__":
    unittest.main()
