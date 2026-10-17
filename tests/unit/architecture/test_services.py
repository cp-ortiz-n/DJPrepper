from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock

from audioextender.analysis.candidate_selection import (
    CandidateSelectionService,
    RankedSelection,
    SelectionRequest,
)
from audioextender.analysis.selection_coordinator import SelectionCoordinator, SideSelectionRequest
from audioextender.analysis.splice_policy import build_splice_plan
from audioextender.core.config import EditConfig
from audioextender.core.interfaces import NullProgressReporter, ProgressReporter
from audioextender.processing.track_processor import TrackProcessor
from tests.support.factories import candidate


class CandidateSelectionServiceTests(unittest.TestCase):
    def test_fixed_length_delegates_through_one_shared_intro_outro_contract(self) -> None:
        ranked = [candidate(unit_bars=4)]
        ranker = Mock(return_value=ranked)
        service = CandidateSelectionService(ranker)
        request = SelectionRequest(
            position="outro",
            maximum_bars=4,
            duration=180.0,
            search_seconds=60.0,
            minimum_start=120.0,
            automatic_length=False,
        )
        result = service.rank(Mock(), request)
        self.assertEqual(result.candidates, tuple(ranked))
        self.assertEqual(result.bars, 4)
        ranker.assert_called_once()
        self.assertEqual(ranker.call_args.args[2], "outro")
        self.assertEqual(ranker.call_args.args[7], 120.0)

    def test_automatic_length_prefers_musically_stronger_choice(self) -> None:
        choices = {
            2: [candidate(unit_bars=2, rhythmic_strength=0.3)],
            4: [candidate(unit_bars=4, rhythmic_strength=0.9)],
        }

        def ranker(_analysis, bars, *_args, **_kwargs):
            return choices[bars]

        result = CandidateSelectionService(ranker).rank(
            Mock(),
            SelectionRequest("intro", 4, 180.0, 60.0),
        )
        self.assertEqual(result.bars, 4)
        self.assertIn("quality", result.reason or "")


class DependencyContractTests(unittest.TestCase):
    def test_null_progress_satisfies_reporter_contract(self) -> None:
        reporter = NullProgressReporter()
        self.assertIsInstance(reporter, ProgressReporter)
        reporter.update(50, "test")
        reporter.log("test")
        reporter.complete()

    def test_splice_plan_groups_all_policy_decisions(self) -> None:
        plan = build_splice_plan(candidate(rhythmic_strength=0.9, vocal_boundary_risk=0.0), 6.0)
        self.assertEqual(plan.mode, "percussion-priority")
        self.assertGreaterEqual(plan.crossfade_ms, 10.0)
        self.assertLessEqual(plan.crossfade_ms, 30.0)
        self.assertLessEqual(plan.tail_ms, 300.0)

    def test_track_processor_accepts_replaceable_pipeline_services(self) -> None:
        stems = Mock()
        selection = Mock()
        exports = Mock()
        processor = TrackProcessor(stems, selection, exports)
        self.assertIs(processor.stem_provider, stems)
        self.assertIs(processor.selection_coordinator, selection)
        self.assertIs(processor.export_service, exports)

    def test_track_processor_rejects_missing_source_before_services_run(self) -> None:
        stems = Mock()
        selection = Mock()
        exports = Mock()
        with self.assertRaises(FileNotFoundError):
            TrackProcessor(stems, selection, exports).process(Path("missing.mp3"), Path("output.wav"), EditConfig())
        stems.analyze.assert_not_called()
        selection.select.assert_not_called()
        exports.export.assert_not_called()


class SelectionCoordinatorTests(unittest.TestCase):
    def test_disabled_side_does_not_invoke_ranking_or_chooser(self) -> None:
        ranking = Mock()
        chooser = Mock()
        result = SelectionCoordinator(ranking).select(
            Mock(),
            180.0,
            None,
            EditConfig(),
            SideSelectionRequest("outro", 0, True, 60.0, 1),
            chooser,
            NullProgressReporter(),
        )
        self.assertIsNone(result.candidate)
        ranking.rank.assert_not_called()
        chooser.assert_not_called()

    def test_automatic_intro_boundary_retries_without_maximum_end(self) -> None:
        chosen = candidate()
        ranking = Mock()
        ranking.rank.side_effect = [
            RuntimeError("no phrase"),
            RankedSelection((chosen,), 4, None),
        ]
        result = SelectionCoordinator(ranking).select(
            Mock(),
            180.0,
            None,
            EditConfig(intro_bars=4, intro_bars_locked=True),
            SideSelectionRequest(
                "intro",
                4,
                True,
                60.0,
                1,
                maximum_end=12.0,
                automatic_boundary=True,
            ),
            lambda options, _position, _rank: (options[0], 1),
            NullProgressReporter(),
        )
        self.assertEqual(ranking.rank.call_count, 2)
        first_request = ranking.rank.call_args_list[0].args[1]
        second_request = ranking.rank.call_args_list[1].args[1]
        self.assertEqual(first_request.maximum_end, 12.0)
        self.assertIsNone(second_request.maximum_end)
        self.assertFalse(result.automatic_boundary)

    def test_outro_uses_minimum_start_and_maximum_end(self) -> None:
        chosen = candidate(section_label="closing")
        ranking = Mock()
        ranking.rank.return_value = RankedSelection((chosen,), 4, None)
        result = SelectionCoordinator(ranking).select(
            Mock(),
            180.0,
            None,
            EditConfig(outro_bars=4, outro_bars_locked=True),
            SideSelectionRequest(
                "outro",
                4,
                True,
                60.0,
                1,
                maximum_end=170.0,
                minimum_start=120.0,
            ),
            lambda options, _position, _rank: (options[0], 1),
            NullProgressReporter(),
        )
        request = ranking.rank.call_args.args[1]
        self.assertEqual(request.maximum_end, 170.0)
        self.assertEqual(request.minimum_start, 120.0)
        self.assertIs(result.candidate, chosen)


if __name__ == "__main__":
    unittest.main()
