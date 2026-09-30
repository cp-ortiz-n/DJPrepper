from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock

import numpy as np

from audioextender.audio.loading import AudioData
from audioextender.core.config import EditConfig
from audioextender.core.interfaces import NullProgressReporter
from audioextender.audio.stem_provider import StemProvider


class StemProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.audio = AudioData(np.zeros((100, 2), dtype=np.float32), 10)
        self.track = Mock(frame_times=np.arange(10, dtype=float))
        self.source = Path("song.mp3")

    def test_disabled_stems_do_not_touch_cache_or_demucs(self) -> None:
        cache = Mock()
        separator = Mock()
        result = StemProvider(separator=separator).analyze(
            self.source,
            self.audio,
            self.track,
            EditConfig(use_stems=False),
            cache,
            NullProgressReporter(),
        )
        self.assertIsNone(result.vocal_energy)
        cache.load_vocals.assert_not_called()
        separator.assert_not_called()

    def test_valid_cache_bypasses_demucs_and_detects_boundaries(self) -> None:
        vocals = np.linspace(0, 1, 10)
        instrumental = AudioData(np.zeros((100, 2), dtype=np.float32), 10)
        cache = Mock()
        cache.load_vocals.return_value = vocals
        cache.load_instrumental.return_value = (instrumental, 0.82)
        cache.load_drums.return_value = instrumental
        separator = Mock()
        detector = Mock(return_value=(3.0, 8.0))
        result = StemProvider(separator, detector).analyze(
            self.source,
            self.audio,
            self.track,
            EditConfig(use_stems=True),
            cache,
            NullProgressReporter(),
        )
        self.assertTrue(result.cache_hit)
        self.assertEqual(result.reliability, 0.82)
        self.assertEqual((result.intro_boundary, result.outro_boundary), (3.0, 8.0))
        separator.assert_not_called()

    def test_fresh_separation_is_cached_and_temporary_files_are_closed(self) -> None:
        vocals = np.linspace(0, 1, 10)
        instrumental = AudioData(np.ones((100, 2), dtype=np.float32), 10)
        separated = Mock(
            vocal_energy=vocals,
            instrumental_audio=instrumental,
            drums_audio=instrumental,
            separation_reliability=0.91,
        )
        separator = Mock(return_value=separated)
        cache = Mock()
        cache.load_vocals.return_value = None
        cache.load_instrumental.return_value = None
        cache.load_drums.return_value = None
        result = StemProvider(separator, Mock(return_value=(None, None))).analyze(
            self.source,
            self.audio,
            self.track,
            EditConfig(use_stems=True),
            cache,
            NullProgressReporter(),
        )
        self.assertFalse(result.cache_hit)
        self.assertEqual(result.reliability, 0.91)
        cache.save_vocals.assert_called_once()
        cache.save_instrumental.assert_called_once()
        cache.save_drums.assert_called_once()
        separated.close.assert_called_once()

    def test_wrong_length_vocal_cache_forces_fresh_separation(self) -> None:
        separated = Mock(
            vocal_energy=np.zeros(10),
            instrumental_audio=self.audio,
            drums_audio=self.audio,
            separation_reliability=0.7,
        )
        cache = Mock()
        cache.load_vocals.return_value = np.zeros(5)
        cache.load_instrumental.return_value = (self.audio, 0.8)
        cache.load_drums.return_value = self.audio
        separator = Mock(return_value=separated)
        StemProvider(separator, Mock(return_value=(None, None))).analyze(
            self.source,
            self.audio,
            self.track,
            EditConfig(use_stems=True),
            cache,
            NullProgressReporter(),
        )
        separator.assert_called_once()
        separated.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
