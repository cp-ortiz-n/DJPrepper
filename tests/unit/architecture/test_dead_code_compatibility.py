from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from audioextender.analysis.key_detection import KeyAnalysis, analyze_key
from audioextender.analysis.section_selector import select_section
from audioextender.audio.loading import AudioData
from audioextender.core.exceptions import AnalysisError, AudioExtenderError
from audioextender.persistence.facade import JobRepository
from tests.support.factories import candidate, track_analysis


class PublicCompatibilityCandidateTests(unittest.TestCase):
    def test_analysis_error_remains_an_expected_runtime_failure(self) -> None:
        self.assertTrue(issubclass(AnalysisError, AudioExtenderError))
        self.assertTrue(issubclass(AnalysisError, RuntimeError))

    def test_key_only_analysis_returns_the_public_result_contract(self) -> None:
        major_profile = np.asarray([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        chroma = np.tile(major_profile[:, None], (1, 24))
        magnitude = np.ones((8, 24), dtype=float)
        audio = AudioData(np.zeros((256, 2), dtype=np.float32), 22_050)
        with (
            patch("audioextender.analysis.key_detection.librosa.to_mono", return_value=np.zeros(256)),
            patch("audioextender.analysis.key_detection.librosa.stft", return_value=magnitude),
            patch("audioextender.analysis.key_detection.librosa.decompose.hpss", return_value=(magnitude, magnitude)),
            patch("audioextender.analysis.key_detection.librosa.feature.chroma_stft", return_value=chroma),
        ):
            result = analyze_key(audio)

        self.assertIsInstance(result, KeyAnalysis)
        self.assertEqual(result.key_label, "C major")
        self.assertGreater(result.confidence, 0)
        self.assertEqual(result.candidates[0]["key"], result.key_label)
        self.assertEqual(result.candidates[0]["selected"], 1.0)

    def test_select_section_preserves_the_single_result_compatibility_contract(self) -> None:
        analysis = track_analysis()
        selected = candidate()
        with patch("audioextender.analysis.section_selector.rank_sections", return_value=[selected]) as rank:
            result = select_section(analysis, 4, "intro", 180.0, 60.0)

        self.assertIs(result, selected)
        rank.assert_called_once_with(
            analysis,
            4,
            "intro",
            180.0,
            60.0,
            None,
            None,
            None,
            count=3,
        )

    def test_key_analysis_update_preserves_unrelated_catalog_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            track_path = root / "track.wav"
            track_path.write_bytes(b"RIFF")
            repository = JobRepository(root / "catalog.sqlite3")
            track_id = repository.upsert_downloaded_track(
                title="Compatible",
                artist="DJ",
                file_path=track_path,
                genre="House",
                genre_category="Electronic / House / House",
            )

            updated = repository.update_downloaded_track_key_analysis(
                track_id,
                detected_key="A minor",
                confidence=87.5,
                candidates=[{"key": "A minor", "confidence": 87.5}],
            )

        self.assertEqual(updated["title"], "Compatible")
        self.assertEqual(updated["genre"], "House")
        self.assertEqual(updated["detected_key"], "A minor")
        self.assertEqual(updated["key_confidence"], 87.5)
        self.assertEqual(json.loads(updated["key_candidates_json"])[0]["key"], "A minor")
        self.assertTrue(updated["key_analyzed_at"])


class PrivateDeadHelperTests(unittest.TestCase):
    def test_confirmed_private_helpers_are_not_part_of_the_runtime_modules(self) -> None:
        from audioextender.processing import extended_edit, track_processor, web_jobs

        self.assertFalse(hasattr(extended_edit, "_choose_splice_mode"))
        self.assertFalse(hasattr(track_processor, "_format_duration"))
        self.assertFalse(hasattr(track_processor, "_print_candidate"))
        self.assertFalse(hasattr(web_jobs, "default_job_values"))


if __name__ == "__main__":
    unittest.main()
