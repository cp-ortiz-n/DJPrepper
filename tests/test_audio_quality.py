import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import soundfile as sf

from audioextender.audio.quality import analyze_audio_quality


class AudioQualityTests(unittest.TestCase):
    def test_clean_full_band_audio_scores_well(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "clean.wav"
            rate = 44100
            time = np.arange(rate * 3) / rate
            signal = .15 * np.sin(2 * np.pi * 1000 * time) + .02 * np.sin(2 * np.pi * 19500 * time)
            sf.write(path, np.column_stack((signal, signal)), rate, subtype="PCM_24")
            result = analyze_audio_quality(path, window_seconds=.25)
            self.assertGreaterEqual(result.score, 75)
            self.assertLess(result.score, 90)
            self.assertEqual(result.label, "good")
            self.assertTrue(any("320 kbps is not verifiable" in note for note in result.notes))
            self.assertEqual(result.sample_rate, rate)
            self.assertEqual(result.bit_depth, 24)
            self.assertEqual(result.target_status, "meets_target")

    def test_transcoded_wav_does_not_claim_the_lossy_bitrate_target(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "converted.wav"
            rate = 48000
            time = np.arange(rate) / rate
            signal = .15 * np.sin(2 * np.pi * 1000 * time)
            sf.write(path, signal, rate, subtype="PCM_16")
            result = analyze_audio_quality(
                path, window_seconds=.25, source_is_transcoded_lossy=True
            )
            self.assertEqual(result.target_status, "unverified")
            self.assertIn("original encoded bitrate", result.target_reason)

    def test_clipped_low_bandwidth_audio_is_flagged(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "poor.wav"
            rate = 44100
            time = np.arange(rate * 3) / rate
            signal = np.clip(3 * np.sin(2 * np.pi * 500 * time), -1, 1)
            sf.write(path, signal, rate, subtype="PCM_16")
            result = analyze_audio_quality(path, window_seconds=.25)
            self.assertLess(result.score, 75)
            self.assertIn(result.label, {"review", "poor"})


if __name__ == "__main__":
    unittest.main()
