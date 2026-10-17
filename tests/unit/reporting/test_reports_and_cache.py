from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from audioextender.infrastructure.cache import AnalysisCache, clear_cache
from audioextender.reporting.processing import update_processing_report


class ProcessingReportTests(unittest.TestCase):
    def test_skipped_song_retains_previous_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            reports = output / "reports"
            reports.mkdir()
            existing = {
                "version": 1,
                "updated_at": "earlier",
                "songs": {
                    "song.mp3": {
                        "source_name": "Song.mp3",
                        "output_name": "Song (Extended Edit).wav",
                        "status": "updated",
                        "updated_at": "earlier",
                        "processing_seconds": 12.0,
                        "bpm": 120.0,
                        "key": "A minor",
                        "intro": None,
                        "outro": None,
                        "mix_in": None,
                        "mix_out": None,
                    }
                },
            }
            (reports / "processing_report.json").write_text(json.dumps(existing))
            _, json_path = update_processing_report(
                output, [], [(Path("Song.mp3"), output / "Song (Extended Edit).wav")]
            )
            record = json.loads(json_path.read_text())["songs"]["song.mp3"]
            self.assertEqual(record["status"], "skipped")
            self.assertEqual(record["bpm"], 120.0)
            self.assertEqual(record["updated_at"], "earlier")


class CacheCleanupTests(unittest.TestCase):
    def test_waveform_cache_persists_and_invalidates_with_audio_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "track.wav"
            source.write_bytes(b"first revision")
            cache = AnalysisCache(root / "cache")
            peaks = np.asarray([0.1, 0.5, 1.0], dtype=np.float32)

            cache.save_waveform(source, 12.5, peaks)
            loaded = cache.load_waveform(source)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded[0], 12.5)
            np.testing.assert_allclose(loaded[1], peaks)

            source.write_bytes(b"second revision with a different size")
            self.assertIsNone(cache.load_waveform(source))

    def test_clear_cache_only_removes_owned_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in ("track.analysis.npz", "track.instrumental.wav", "keep.txt"):
                (directory / name).touch()
            self.assertEqual(clear_cache(directory), 2)
            self.assertTrue((directory / "keep.txt").exists())


if __name__ == "__main__":
    unittest.main()
