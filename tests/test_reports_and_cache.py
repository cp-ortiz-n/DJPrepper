from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from helpers.cache import clear_cache
from helpers.processing_report import update_processing_report


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
    def test_clear_cache_only_removes_owned_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in ("track.analysis.npz", "track.instrumental.wav", "keep.txt"):
                (directory / name).touch()
            self.assertEqual(clear_cache(directory), 2)
            self.assertTrue((directory / "keep.txt").exists())


if __name__ == "__main__":
    unittest.main()
