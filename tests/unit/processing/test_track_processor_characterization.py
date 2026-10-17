"""Behavioral baseline for the single-track processing transaction.

These tests intentionally describe the current public orchestration contract.
They should remain stable while ARCH-002B moves the implementation into typed
stages, unless a deliberate compatibility change updates this baseline first.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock, patch, sentinel

import numpy as np

from audioextender.analysis.candidate_validator import ValidationResult
from audioextender.analysis.selection_coordinator import SideSelectionResult
from audioextender.audio.loading import AudioData
from audioextender.audio.stem_provider import StemAnalysis
from audioextender.core.config import EditConfig
from audioextender.library.export_service import ExportResult
from audioextender.processing.track_processor import TrackProcessor
from tests.support.factories import candidate, track_analysis


class RecordingProgress:
    """Progress spy that implements the complete reporter protocol."""

    def __init__(self) -> None:
        self.updates: list[tuple[float, str]] = []
        self.logs: list[str] = []
        self.completions: list[str] = []
        self.stop_count = 0

    def update(self, percent: float, label: str) -> None:
        self.updates.append((percent, label))

    def log(self, message: str) -> None:
        self.logs.append(message)

    def complete(self, label: str = "Complete") -> None:
        self.completions.append(label)

    def stop(self) -> None:
        self.stop_count += 1

    def pause_for_input(self) -> None:
        pass

    def resume_after_input(self) -> None:
        pass


class MemoryAnalysisCache:
    """Small cache double used to expose hit, miss, save, and refresh behavior."""

    stored = None

    def __init__(self, _directory: Path, enabled: bool = True, refresh: bool = False) -> None:
        self.enabled = enabled
        self.refresh = refresh

    def load_analysis(self, _source: Path, _config: EditConfig):
        if not self.enabled or self.refresh:
            return None
        return type(self).stored

    def save_analysis(self, _source: Path, _config: EditConfig, analysis) -> None:
        if self.enabled:
            type(self).stored = analysis

    def load_drums(self, _source: Path, _config: EditConfig):
        return None

    def load_instrumental(self, _source: Path, _config: EditConfig):
        return None


class TrackProcessorCharacterizationTests(unittest.TestCase):
    def setUp(self) -> None:
        MemoryAnalysisCache.stored = None
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.wav"
        self.source.touch()
        self.output = self.root / "extended" / "source (Extended Edit).wav"
        self.audio = AudioData(np.zeros((960, 2), dtype=np.float32), 60)
        self.analysis = track_analysis()
        self.readiness = SimpleNamespace(
            intro=SimpleNamespace(mixable_bars=0),
            outro=SimpleNamespace(mixable_bars=0),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _config(self, **changes: Any) -> EditConfig:
        base = EditConfig(
            intro_bars=4,
            outro_bars=4,
            intro_bars_locked=True,
            outro_bars_locked=True,
            use_stems=False,
            cache_directory=str(self.root / "cache"),
            export_cues=False,
        )
        return replace(base, **changes)

    @staticmethod
    def _selection(position: str) -> SideSelectionResult:
        chosen = candidate(section_label="opening" if position == "intro" else "closing")
        return SideSelectionResult(chosen, 1, (chosen,), None, None, False, False)

    def _processor(self, events: list[str], *, stems: StemAnalysis | None = None) -> TrackProcessor:
        stem_provider = Mock()

        def analyze_stems(*_args: Any) -> StemAnalysis:
            events.append("stems")
            return stems or StemAnalysis()

        stem_provider.analyze.side_effect = analyze_stems
        selection = Mock()

        def select(_analysis: Any, _duration: Any, _vocals: Any, _config: Any, request: Any, *_args: Any):
            events.append(f"select:{request.position}")
            return self._selection(request.position)

        selection.select.side_effect = select
        exporter = Mock()

        def export(*_args: Any) -> ExportResult:
            events.append("export")
            return ExportResult(
                True,
                self.root / "previews" / "intro.wav",
                self.root / "previews" / "outro.wav",
                (),
                self.root / "cues" / "source.json",
            )

        exporter.export.side_effect = export
        validator = Mock()

        def validate(chosen: Any, *_args: Any, **kwargs: Any) -> ValidationResult:
            events.append(f"validate:{kwargs['position']}")
            return ValidationResult(chosen, None, False)

        validator.validate.side_effect = validate
        return TrackProcessor(stem_provider, selection, exporter, validator)

    def test_full_pipeline_freezes_stage_order_progress_artifacts_and_timing(self) -> None:
        events: list[str] = []
        progress = RecordingProgress()
        processor = self._processor(events)

        def analyze(_audio, _config, report):
            events.append("analysis")
            report(0.25, "Detecting beat grid")
            report(0.75, "Estimating musical key")
            return self.analysis

        def load(_path: Path) -> AudioData:
            events.append("load")
            return self.audio

        def render(*_args: Any) -> AudioData:
            events.append("render")
            return self.audio

        clock = iter(float(value) for value in range(30))
        with (
            patch(
                "audioextender.processing.analysis_preparation.load_audio",
                side_effect=load,
            ),
            patch("audioextender.processing.analysis_preparation.AnalysisCache", MemoryAnalysisCache),
            patch("audioextender.processing.analysis_preparation.analyze_track", side_effect=analyze),
            patch("audioextender.processing.analysis_preparation.detect_dj_readiness", return_value=self.readiness),
            patch(
                "audioextender.processing.candidate_selection_orchestration.optimize_candidate_boundaries",
                side_effect=lambda _audio, item: item,
            ),
            patch(
                "audioextender.processing.render_export_transaction.create_extended_edit",
                side_effect=render,
            ),
            patch("audioextender.processing.track_processor.time.monotonic", side_effect=lambda: next(clock)),
            patch("audioextender.processing.analysis_preparation.time.monotonic", side_effect=lambda: next(clock)),
        ):
            result = processor.process(self.source, self.output, self._config(), progress)

        self.assertEqual(
            events,
            [
                "load",
                "analysis",
                "stems",
                "select:intro",
                "select:outro",
                "validate:intro",
                "validate:outro",
                "render",
                "export",
            ],
        )
        self.assertEqual(
            progress.updates,
            [
                (0, "Loading audio"),
                (8, "Starting audio analysis"),
                (23.5, "Detecting beat grid"),
                (54.5, "Estimating musical key"),
                (80, "Scoring intro phrases"),
                (85, "Scoring outro phrases"),
                (88, "Optimizing loop boundaries"),
                (90, "Assembling extended edit"),
            ],
        )
        self.assertEqual(
            [label for label, _duration in result.stage_timings],
            [
                "Loading audio",
                "Starting audio analysis",
                "Detecting beat grid",
                "Estimating musical key",
                "Vocal and stem analysis",
                "Total",
            ],
        )
        # The result captures elapsed time immediately before final assembly;
        # the Total timing is sampled once more while constructing the result.
        self.assertEqual(result.elapsed, 9.0)
        self.assertEqual(result.stage_timings[-1][1], 10.0)
        self.assertGreaterEqual(result.stage_timings[-1][1], result.elapsed)
        self.assertTrue(all(duration >= 0 for _label, duration in result.stage_timings))
        self.assertEqual(result.intro_preview, self.root / "previews" / "intro.wav")
        self.assertEqual(result.outro_preview, self.root / "previews" / "outro.wav")
        self.assertEqual(result.cue_sheet, self.root / "cues" / "source.json")
        self.assertEqual(result.wav_output, self.root / "wav" / "source.wav")
        self.assertTrue(result.full_exported)
        self.assertEqual(progress.stop_count, 0)

    def test_analysis_cache_miss_hit_and_refresh_are_visible_in_result_and_progress(self) -> None:
        analyze = Mock(return_value=self.analysis)
        stem_provider = Mock()
        stem_provider.analyze.return_value = StemAnalysis(cache_hit=True)
        processor = TrackProcessor(stem_provider=stem_provider)

        def run(*, refresh: bool = False):
            progress = RecordingProgress()
            with (
                patch("audioextender.processing.analysis_preparation.load_audio", return_value=self.audio),
                patch("audioextender.processing.analysis_preparation.AnalysisCache", MemoryAnalysisCache),
                patch("audioextender.processing.analysis_preparation.analyze_track", analyze),
                patch("audioextender.processing.analysis_preparation.detect_dj_readiness", return_value=self.readiness),
            ):
                result = processor.process(
                    self.source,
                    self.output,
                    self._config(analysis_only=True, refresh_cache=refresh),
                    progress,
                )
            return result, progress

        miss, miss_progress = run()
        hit, hit_progress = run()
        refreshed, refresh_progress = run(refresh=True)

        self.assertFalse(miss.analysis_cache_hit)
        self.assertTrue(hit.analysis_cache_hit)
        self.assertFalse(refreshed.analysis_cache_hit)
        self.assertTrue(miss.vocal_cache_hit)
        self.assertEqual(analyze.call_count, 2)
        self.assertIn("Saved track analysis to cache", miss_progress.logs)
        self.assertIn((70, "Loaded cached track analysis"), hit_progress.updates)
        self.assertIn("Loaded track analysis from cache", hit_progress.logs)
        self.assertNotIn((70, "Loaded cached track analysis"), refresh_progress.updates)
        self.assertEqual(hit.output, self.source)
        self.assertEqual(hit.wav_output, self.source)
        self.assertFalse(self.output.exists())

    def test_stem_configuration_is_forwarded_and_reported_without_changing_stage_order(self) -> None:
        events: list[str] = []
        instrumental = AudioData(np.zeros((960, 2), dtype=np.float32), 60)
        processor = self._processor(
            events,
            stems=StemAnalysis(
                vocal_energy=np.zeros(len(self.analysis.frame_times)),
                instrumental_audio=instrumental,
                reliability=0.95,
                cache_hit=True,
            ),
        )
        progress = RecordingProgress()
        with (
            patch("audioextender.processing.analysis_preparation.load_audio", return_value=self.audio),
            patch("audioextender.processing.analysis_preparation.AnalysisCache", MemoryAnalysisCache),
            patch("audioextender.processing.analysis_preparation.analyze_track", return_value=self.analysis),
            patch("audioextender.processing.analysis_preparation.detect_dj_readiness", return_value=self.readiness),
            patch(
                "audioextender.processing.candidate_selection_orchestration.optimize_candidate_boundaries",
                side_effect=lambda _audio, item: item,
            ),
            patch("audioextender.processing.render_export_transaction.create_extended_edit", return_value=self.audio),
        ):
            result = processor.process(self.source, self.output, self._config(use_stems=True), progress)

        stem_config = cast(Mock, processor.stem_provider.analyze).call_args.args[3]
        self.assertTrue(stem_config.use_stems)
        self.assertEqual(result.stem_reliability, 0.95)
        self.assertTrue(result.vocal_cache_hit)
        self.assertLess(events.index("stems"), events.index("select:intro"))

    def test_each_pipeline_failure_stops_progress_and_skips_later_stages(self) -> None:
        failure_cases = ("loading", "analysis", "stems", "selection", "render", "export")
        for failing_stage in failure_cases:
            with self.subTest(stage=failing_stage):
                events: list[str] = []
                progress = RecordingProgress()
                processor = self._processor(events)
                if failing_stage == "stems":
                    cast(Mock, processor.stem_provider.analyze).side_effect = RuntimeError("stems failed")
                if failing_stage == "selection":
                    cast(Mock, processor.selection_coordinator.select).side_effect = RuntimeError("selection failed")
                if failing_stage == "export":
                    cast(Mock, processor.export_service.export).side_effect = RuntimeError("export failed")

                def load(_path, *, _events=events, _failing=failing_stage):
                    _events.append("load")
                    if _failing == "loading":
                        raise RuntimeError("loading failed")
                    return self.audio

                def analyze(_audio, _config, _report, *, _events=events, _failing=failing_stage):
                    _events.append("analysis")
                    if _failing == "analysis":
                        raise RuntimeError("analysis failed")
                    return self.analysis

                def render(*_args, _events=events, _failing=failing_stage):
                    _events.append("render")
                    if _failing == "render":
                        raise RuntimeError("render failed")
                    return self.audio

                with (
                    patch("audioextender.processing.analysis_preparation.load_audio", side_effect=load),
                    patch("audioextender.processing.analysis_preparation.AnalysisCache", MemoryAnalysisCache),
                    patch("audioextender.processing.analysis_preparation.analyze_track", side_effect=analyze),
                    patch(
                        "audioextender.processing.analysis_preparation.detect_dj_readiness",
                        return_value=self.readiness,
                    ),
                    patch(
                        "audioextender.processing.candidate_selection_orchestration.optimize_candidate_boundaries",
                        side_effect=lambda _audio, item: item,
                    ),
                    patch(
                        "audioextender.processing.render_export_transaction.create_extended_edit",
                        side_effect=render,
                    ),
                ):
                    with self.assertRaisesRegex(RuntimeError, f"{failing_stage} failed"):
                        processor.process(self.source, self.output, self._config(), progress)

                self.assertEqual(progress.stop_count, 1)
                self.assertFalse(self.output.exists())
                if failing_stage in {"loading", "analysis", "stems", "selection", "render"}:
                    cast(Mock, processor.export_service.export).assert_not_called()

    def test_facade_delegates_to_explicit_stage_owners(self) -> None:
        progress = RecordingProgress()
        analysis = SimpleNamespace(config=SimpleNamespace(analysis_only=False))
        analysis_preparation = Mock()
        analysis_preparation.prepare.return_value = analysis
        candidate_selection = Mock()
        candidate_selection.select.return_value = sentinel.selection
        render_export = Mock()
        render_export.execute.return_value = (sentinel.render, sentinel.exported)
        result_builder = Mock()
        result_builder.completed.return_value = sentinel.result
        failure_cleanup = Mock()
        processor = TrackProcessor(
            analysis_preparation=analysis_preparation,
            candidate_selection=candidate_selection,
            render_export=render_export,
            result_builder=result_builder,
            failure_cleanup=failure_cleanup,
        )

        result = processor.process(self.source, self.output, self._config(), progress, 10.0, 120.0, 160.0)

        self.assertIs(result, sentinel.result)
        analysis_preparation.prepare.assert_called_once_with(self.source, self._config(), progress, 10.0, 120.0)
        candidate_selection.select.assert_called_once_with(self.source, self.output, analysis, progress, 160.0)
        render_export.execute.assert_called_once_with(
            self.source,
            self.output,
            analysis,
            sentinel.selection,
            progress,
        )
        result_builder.completed.assert_called_once()
        failure_cleanup.run.assert_not_called()

    def test_analysis_only_result_skips_selection_render_and_export(self) -> None:
        progress = RecordingProgress()
        analysis = SimpleNamespace(config=SimpleNamespace(analysis_only=True))
        analysis_preparation = Mock()
        analysis_preparation.prepare.return_value = analysis
        candidate_selection = Mock()
        render_export = Mock()
        result_builder = Mock()
        result_builder.analysis_only.return_value = sentinel.analysis_result
        processor = TrackProcessor(
            analysis_preparation=analysis_preparation,
            candidate_selection=candidate_selection,
            render_export=render_export,
            result_builder=result_builder,
        )

        result = processor.process(self.source, self.output, self._config(), progress)

        self.assertIs(result, sentinel.analysis_result)
        self.assertIn((100, "Analysis complete"), progress.updates)
        candidate_selection.select.assert_not_called()
        render_export.execute.assert_not_called()
        result_builder.completed.assert_not_called()

    def test_failure_cleanup_owns_reporter_shutdown(self) -> None:
        progress = RecordingProgress()
        analysis_preparation = Mock()
        analysis_preparation.prepare.side_effect = RuntimeError("analysis failed")
        failure_cleanup = Mock()
        processor = TrackProcessor(
            analysis_preparation=analysis_preparation,
            failure_cleanup=failure_cleanup,
        )

        with self.assertRaisesRegex(RuntimeError, "analysis failed"):
            processor.process(self.source, self.output, self._config(), progress)

        failure_cleanup.run.assert_called_once_with(progress)


if __name__ == "__main__":
    unittest.main()
