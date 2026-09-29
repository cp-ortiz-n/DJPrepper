from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from helpers.batch_runner import BatchRunner
from helpers.candidate_validator import CandidateValidator
from helpers.config import EditConfig
from helpers.config_factory import ConfigFactory
from main import _parser
from tests.factories import candidate


class CandidateValidatorTests(unittest.TestCase):
    def test_default_intro_floor_rejects_weak_loop(self) -> None:
        result = CandidateValidator().validate(
            candidate(
                seam_compatibility=0.4,
                timbre_compatibility=0.4,
                bass_compatibility=0.4,
            ),
            EditConfig(),
            None,
            0.0,
            False,
            position="intro",
        )
        self.assertIsNone(result.candidate)
        self.assertIn("below 65%", result.rejection_reason or "")

    def test_default_outro_floor_also_rejects_weak_loop(self) -> None:
        result = CandidateValidator().validate(
            candidate(
                seam_compatibility=0.4,
                timbre_compatibility=0.4,
                bass_compatibility=0.4,
            ),
            EditConfig(),
            None,
            0.0,
            False,
            position="outro",
        )
        self.assertIsNone(result.candidate)
        self.assertIn("below 65%", result.rejection_reason or "")

    def test_exposed_melodic_intro_is_rejected_automatically(self) -> None:
        result = CandidateValidator().validate(
            candidate(rhythmic_strength=0.04, instrumentalness=0.25),
            EditConfig(),
            None,
            0.0,
            False,
            position="intro",
        )
        self.assertIsNone(result.candidate)
        self.assertIn("exposed melodic phrase", result.rejection_reason or "")

    def test_same_sparse_material_is_not_blanket_rejected_as_an_outro(self) -> None:
        result = CandidateValidator().validate(
            candidate(rhythmic_strength=0.04, instrumentalness=0.25),
            EditConfig(),
            None,
            0.0,
            False,
            position="outro",
        )
        self.assertIsNotNone(result.candidate)

    def test_same_validator_rejects_buildup_for_either_side(self) -> None:
        result = CandidateValidator().validate(
            candidate(buildup_risk=0.9), EditConfig(), None, 0.0, False
        )
        self.assertIsNone(result.candidate)
        self.assertIn("buildup", result.rejection_reason or "")

    def test_repetition_cap_returns_adjusted_immutable_candidate(self) -> None:
        original = candidate(repetitions=5)
        result = CandidateValidator().validate(
            original, EditConfig(maximum_repetitions=2), None, 0.0, False
        )
        self.assertEqual(original.repetitions, 5)
        self.assertIsNotNone(result.candidate)
        assert result.candidate is not None
        self.assertEqual(result.candidate.repetitions, 2)
        self.assertTrue(result.shortened)

    def test_explicit_review_choice_bypasses_automatic_quality_rejection(self) -> None:
        chosen = candidate(
            seam_compatibility=0.2,
            timbre_compatibility=0.2,
            bass_compatibility=0.2,
            arrangement_fit=-0.8,
        )
        result = CandidateValidator().validate(
            chosen,
            EditConfig(manual_candidate_selection=True),
            None,
            0.0,
            False,
            position="intro",
        )
        self.assertEqual(result.candidate, chosen)
        self.assertIsNone(result.rejection_reason)


class ConfigFactoryTests(unittest.TestCase):
    def test_cli_value_overrides_preset_value(self) -> None:
        args = _parser().parse_args(["--preset", "club", "--intro-bars", "2"])
        config = ConfigFactory.from_arguments(args)
        self.assertEqual(config.intro_bars, 2)
        self.assertEqual(config.outro_bars, 16)
        self.assertTrue(config.intro_bars_locked)

    def test_invalid_manual_boundary_is_rejected_centrally(self) -> None:
        args = _parser().parse_args(["--intro-before", "0"])
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            ConfigFactory.from_arguments(args)


class BatchRunnerTests(unittest.TestCase):
    @patch("helpers.batch_runner.process_file")
    def test_single_job_uses_serial_processor(self, process_file) -> None:
        process_file.return_value = Mock(elapsed=1.5)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "song.wav"
            source.touch()
            jobs: list[tuple[Path, Path, float | None, float | None, float | None]] = [
                (source, root / "out.wav", None, None, None)
            ]
            with redirect_stdout(StringIO()):
                results, failures = BatchRunner().run(jobs, EditConfig(), workers=3)
        self.assertEqual(len(results), 1)
        self.assertEqual(failures, [])
        process_file.assert_called_once()


if __name__ == "__main__":
    unittest.main()
