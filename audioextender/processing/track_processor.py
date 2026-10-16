"""Stable facade for the single-track processing transaction."""

from __future__ import annotations

import time
from pathlib import Path

from audioextender.analysis.candidate_validator import CandidateValidator
from audioextender.analysis.key_detection import TrackAnalysis
from audioextender.analysis.selection_coordinator import SelectionCoordinator
from audioextender.audio.stem_provider import StemProvider
from audioextender.core.config import EditConfig
from audioextender.core.interfaces import ProgressReporter
from audioextender.core.models import FileResult
from audioextender.infrastructure.progress import ProgressBar
from audioextender.library.export_service import ExportService
from audioextender.processing.analysis_preparation import AnalysisPreparationService
from audioextender.processing.candidate_selection_orchestration import (
    CandidateSelectionOrchestrator,
    parse_timestamp,
)
from audioextender.processing.processing_failure_cleanup import ProcessingFailureCleanup
from audioextender.processing.render_export_transaction import RenderExportTransaction
from audioextender.processing.track_processing_stages import arrangement_sections
from audioextender.processing.track_result_builder import TrackResultBuilder


def _parse_timestamp(value: str) -> float:
    """Compatibility wrapper for the historical CLI helper."""
    return parse_timestamp(value)


def _arrangement_sections(analysis: TrackAnalysis):
    """Compatibility wrapper for callers using the former private helper."""
    return arrangement_sections(analysis)


class TrackProcessor:
    """Coordinate focused stages while preserving the public processing API."""

    def __init__(
        self,
        stem_provider: StemProvider | None = None,
        selection_coordinator: SelectionCoordinator | None = None,
        export_service: ExportService | None = None,
        candidate_validator: CandidateValidator | None = None,
        analysis_preparation: AnalysisPreparationService | None = None,
        candidate_selection: CandidateSelectionOrchestrator | None = None,
        render_export: RenderExportTransaction | None = None,
        result_builder: TrackResultBuilder | None = None,
        failure_cleanup: ProcessingFailureCleanup | None = None,
    ) -> None:
        self.stem_provider = stem_provider or StemProvider()
        self.selection_coordinator = selection_coordinator or SelectionCoordinator()
        self.export_service = export_service or ExportService()
        self.candidate_validator = candidate_validator or CandidateValidator()
        self.analysis_preparation = analysis_preparation or AnalysisPreparationService(self.stem_provider)
        self.candidate_selection = candidate_selection or CandidateSelectionOrchestrator(
            self.stem_provider,
            self.selection_coordinator,
            self.export_service,
            self.candidate_validator,
        )
        self.render_export = render_export or RenderExportTransaction(self.export_service)
        self.result_builder = result_builder or TrackResultBuilder()
        self.failure_cleanup = failure_cleanup or ProcessingFailureCleanup()

    def process(
        self,
        source: Path,
        output: Path,
        config: EditConfig,
        progress: ProgressReporter | None = None,
        intro_before: float | None = None,
        outro_after: float | None = None,
        outro_before: float | None = None,
    ) -> FileResult:
        """Analyze and render one input file through explicit stage owners."""
        if not source.is_file():
            raise FileNotFoundError(source)
        if output == source:
            raise ValueError("Output path must differ from input path")

        started = time.monotonic()
        reporter = progress or ProgressBar(show_logs=config.choose_candidates)
        try:
            analysis = self.analysis_preparation.prepare(source, config, reporter, intro_before, outro_after)
            if analysis.config.analysis_only:
                reporter.update(100, "Analysis complete")
                return self.result_builder.analysis_only(source, started, analysis, time.monotonic)
            selection = self.candidate_selection.select(source, output, analysis, reporter, outro_before)
            render, exported = self.render_export.execute(source, output, analysis, selection, reporter)
        except Exception:
            self.failure_cleanup.run(reporter)
            raise
        return self.result_builder.completed(
            source,
            output,
            started,
            analysis,
            selection,
            render,
            exported,
            time.monotonic,
        )


def process_file(
    source: Path,
    output: Path,
    config: EditConfig,
    progress: ProgressReporter | None = None,
    intro_before: float | None = None,
    outro_after: float | None = None,
    outro_before: float | None = None,
) -> FileResult:
    """Backward-compatible functional entry point for existing callers."""
    return TrackProcessor().process(
        source,
        output,
        config,
        progress,
        intro_before,
        outro_after,
        outro_before,
    )
