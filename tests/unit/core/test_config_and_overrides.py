from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from audioextender.core.config import EditConfig
from audioextender.library.track_overrides import load_track_overrides


class EditConfigTests(unittest.TestCase):
    def test_default_configuration_is_valid(self) -> None:
        EditConfig().validate()

    def test_rejects_unsupported_bar_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "intro bars"):
            EditConfig(intro_bars=3).validate()

    def test_rejects_invalid_preview_and_candidate_count(self) -> None:
        with self.assertRaisesRegex(ValueError, "preview seconds"):
            EditConfig(preview_seconds=0).validate()
        with self.assertRaisesRegex(ValueError, "candidate count"):
            EditConfig(candidate_count=0).validate()


class TrackOverrideTests(unittest.TestCase):
    def test_missing_file_means_no_overrides(self) -> None:
        self.assertEqual(load_track_overrides(Path("does-not-exist.json")), {})

    def test_keys_are_case_insensitive_and_numbers_are_coerced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "overrides.json"
            path.write_text(json.dumps({"Song.MP3": {"intro_before": 12}}))
            loaded = load_track_overrides(path)
        self.assertEqual(loaded["song.mp3"].intro_before, 12.0)

    def test_rejects_non_positive_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "overrides.json"
            path.write_text(json.dumps({"song.mp3": {"outro_after": 0}}))
            with self.assertRaisesRegex(ValueError, "positive number"):
                load_track_overrides(path)


if __name__ == "__main__":
    unittest.main()
