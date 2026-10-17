from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np

from audioextender.analysis.selection_coordinator import SideSelectionResult
from audioextender.audio.loading import AudioData
from audioextender.core.config import EditConfig
from audioextender.library.export_service import ExportResult
from audioextender.processing.track_processing_stages import (
    AnalysisStageResult,
    ExportStageResult,
    RenderStageResult,
    SelectionStageResult,
    arrangement_sections,
)
from audioextender.processing.track_result_builder import TrackResultBuilder
from tests.support.factories import candidate, track_analysis


class TrackProcessingStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analysis = track_analysis()
        self.audio = AudioData(np.zeros((600, 2), dtype=np.float32), 60)
        self.config = EditConfig(intro_bars=4, outro_bars=4, intro_bars_locked=True, outro_bars_locked=True)
        self.readiness = SimpleNamespace(
            intro=SimpleNamespace(mixable_bars=0),
            outro=SimpleNamespace(mixable_bars=0),
        )
        self.analysis_stage = AnalysisStageResult(
            audio=self.audio,
            analysis=self.analysis,
            cache=cast(Any, SimpleNamespace()),
            config=self.config,
            analysis_cache_hit=False,
            vocal_energy=None,
            instrumental_audio=None,
            drums_audio=None,
            stem_reliability=0.0,
            vocal_cache_hit=False,
            intro_before=None,
            outro_after=None,
            automatic_intro_boundary=False,
            automatic_outro_boundary=False,
            detected_style=None,
            preset_reason=None,
            section_profiles=(),
            readiness=cast(Any, self.readiness),
            stage_timings=(("Loading audio", 0.1),),
        )

    def test_stage_results_are_immutable_transaction_boundaries(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self.analysis_stage.analysis_cache_hit = True  # type: ignore[misc]

    def test_analysis_result_preserves_public_metrics_and_timing(self) -> None:
        result = TrackResultBuilder.analysis_only(Path("track.wav"), 10.0, self.analysis_stage, lambda: 12.5)

        self.assertEqual(result.output, Path("track.wav"))
        self.assertEqual(result.bpm, self.analysis.bpm)
        self.assertEqual(result.output_duration, self.audio.duration)
        self.assertEqual(result.stage_timings, (("Loading audio", 0.1), ("Total", 2.5)))

    def test_final_result_uses_stage_outputs_for_artifacts_and_construction(self) -> None:
        intro = candidate(start=4.0, end=8.0, repetitions=2)
        outro = candidate(start=30.0, end=34.0, repetitions=2)
        selection = SelectionStageResult(
            config=self.config,
            intro=intro,
            outro=outro,
            intro_selection=SideSelectionResult(intro, 1, (intro,), None, None, False, False),
            outro_selection=SideSelectionResult(outro, 1, (outro,), None, None, False, False),
            reviews={},
            intro_before=None,
            outro_after=None,
            outro_before=None,
            automatic_intro_boundary=False,
            automatic_outro_boundary=False,
            intro_candidate_rank=1,
            outro_candidate_rank=1,
            intro_rejection_reason=None,
            outro_rejection_reason=None,
            intro_fallback=None,
            outro_fallback=None,
            intro_already_ready=False,
            outro_already_ready=False,
            redrum_intro=False,
            high_quality_drums=None,
            instrumental_audio=None,
            stem_reliability=0.0,
            vocal_cache_hit=False,
        )
        rendered = RenderStageResult(self.audio, False, False)
        artifacts = ExportResult(True, Path("intro.wav"), Path("outro.wav"), (), Path("cues.json"))
        exported = ExportStageResult(Path("wav/track.wav"), artifacts)
        clock = iter((13.0, 14.0))

        result = TrackResultBuilder.completed(
            Path("track.wav"),
            Path("extended.wav"),
            10.0,
            self.analysis_stage,
            selection,
            rendered,
            exported,
            lambda: next(clock),
        )

        self.assertEqual(result.wav_output, Path("wav/track.wav"))
        self.assertEqual(result.intro_preview, Path("intro.wav"))
        self.assertEqual(result.outro_preview, Path("outro.wav"))
        self.assertEqual(result.cue_sheet, Path("cues.json"))
        self.assertEqual(result.intro_construction, "full mix")
        self.assertEqual(result.outro_construction, "full mix")
        self.assertEqual(result.elapsed, 3.0)
        self.assertEqual(result.stage_timings[-1], ("Total", 4.0))

    def test_arrangement_sections_still_merge_adjacent_labels(self) -> None:
        sections = arrangement_sections(self.analysis)
        for left, right in zip(sections, sections[1:], strict=False):
            self.assertNotEqual(left.label, right.label)


if __name__ == "__main__":
    unittest.main()
