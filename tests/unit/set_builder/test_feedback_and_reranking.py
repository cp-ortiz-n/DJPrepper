from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from audioextender.analysis.candidate_reranker import assess_candidate, rerank_candidates
from audioextender.reporting.feedback import append_candidate_feedback
from tests.support.factories import candidate


class CandidateQualityTests(unittest.TestCase):
    def test_scores_measure_distinct_concerns(self) -> None:
        clean = candidate()
        bad_transition = candidate(
            bass_reset_risk=0.9,
            energy_context_match=0.1,
            context_compatibility=0.1,
        )
        self.assertGreater(clean.transition_quality, bad_transition.transition_quality)
        self.assertGreater(clean.loop_quality, bad_transition.loop_quality)

    def test_slow_style_prioritizes_musical_phrase_and_transition(self) -> None:
        technical = candidate(
            start=20.0,
            end=24.0,
            arrangement_fit=-0.2,
            context_compatibility=0.4,
            energy_context_match=0.4,
        )
        musical = candidate(
            start=4.0,
            end=8.0,
            seam_compatibility=0.65,
            arrangement_fit=0.9,
            context_compatibility=0.95,
            energy_context_match=0.95,
        )
        ranked = rerank_candidates([technical, musical], "intro", "slow-song")
        self.assertIs(ranked[0], musical)

    def test_assessment_explains_risky_candidate(self) -> None:
        assessment = assess_candidate(candidate(buildup_risk=0.8, bass_reset_risk=0.7), "intro", "club")
        self.assertIn("buildup may reset", assessment.warnings)
        self.assertIn("bass may disappear at repeat", assessment.warnings)

    def test_regional_context_changes_candidate_ranking(self) -> None:
        compatible = candidate(
            regional_style="sparse/ambient",
            regional_compatibility=0.92,
            regional_boundary_risk=0.05,
        )
        conflicting = candidate(
            start=12.0,
            end=16.0,
            regional_style="high-energy",
            regional_compatibility=0.35,
            regional_boundary_risk=0.70,
        )
        ranked = rerank_candidates([conflicting, compatible], "intro", "subtle")
        self.assertIs(ranked[0], compatible)
        warning = assess_candidate(conflicting, "intro", "subtle").warnings
        self.assertIn("crosses or conflicts with a musical region", warning)


class FeedbackReportTests(unittest.TestCase):
    @staticmethod
    def _result() -> SimpleNamespace:
        option = candidate()
        return SimpleNamespace(
            source_name="Song.mp3",
            preset_name="auto → subtle",
            detected_style="mixed/subtle",
            intro_candidates=(option,),
            outro_candidates=(replace(option, start=120.0, end=124.0),),
            intro_candidate_rank=1,
            outro_candidate_rank=1,
            intro_review_reason=None,
            intro_review_notes=None,
            outro_review_reason=None,
            outro_review_notes=None,
        )

    def test_append_only_report_preserves_user_notes_and_avoids_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            path = append_candidate_feedback(output, [self._result()])
            original = path.read_text()
            path.write_text(original.replace("Listening notes: ", "Listening notes: keep me"))
            append_candidate_feedback(output, [self._result()])
            updated = path.read_text()
            self.assertIn("Listening notes: keep me", updated)
            self.assertEqual(updated.count("## Song.mp3"), 1)

    def test_changed_candidates_append_a_new_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            result = self._result()
            path = append_candidate_feedback(output, [result])
            changed = SimpleNamespace(
                **{
                    **result.__dict__,
                    "intro_candidates": (replace(candidate(), start=12.0, end=16.0),),
                }
            )
            append_candidate_feedback(output, [changed])
            self.assertEqual(path.read_text().count("## Song.mp3"), 2)


if __name__ == "__main__":
    unittest.main()
