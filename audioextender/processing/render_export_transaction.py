"""In-memory rendering and durable export for one selected track."""

from __future__ import annotations

from pathlib import Path

from audioextender.audio.loading import AudioData
from audioextender.audio.redrum import create_redrum_intro
from audioextender.core.defaults import WAV_OUTPUT_FOLDER_NAME
from audioextender.core.interfaces import ProgressReporter
from audioextender.library.export_service import ExportRequest, ExportService
from audioextender.processing.candidate_selection_orchestration import format_time
from audioextender.processing.extended_edit import create_extended_edit, insert_audio_region, should_use_instrumental
from audioextender.processing.track_processing_stages import (
    AnalysisStageResult,
    ExportStageResult,
    RenderStageResult,
    SelectionStageResult,
)


class RenderExportTransaction:
    """Render selected edits and persist every output through one boundary."""

    def __init__(self, export_service: ExportService) -> None:
        self._export_service = export_service

    def execute(
        self,
        source: Path,
        output: Path,
        analysis_stage: AnalysisStageResult,
        selection: SelectionStageResult,
        progress: ProgressReporter,
    ) -> tuple[RenderStageResult, ExportStageResult]:
        render = self._render(analysis_stage, selection, progress)
        exported = self._export(source, output, analysis_stage, selection, render.edited_audio, progress)
        return render, exported

    @staticmethod
    def _render(
        analysis_stage: AnalysisStageResult,
        selection: SelectionStageResult,
        progress: ProgressReporter,
    ) -> RenderStageResult:
        audio = analysis_stage.audio
        config = selection.config
        intro = selection.intro
        outro = selection.outro
        instrumental_audio = selection.instrumental_audio
        progress.update(90, "Assembling extended edit")
        intro_uses_stems = not selection.redrum_intro and should_use_instrumental(
            intro,
            instrumental_audio,
            selection.stem_reliability,
            config.minimum_stem_construction_reliability,
            config.minimum_vocal_coverage_for_instrumental_edit,
        )
        outro_uses_stems = should_use_instrumental(
            outro,
            instrumental_audio,
            selection.stem_reliability,
            config.minimum_stem_construction_reliability,
            config.minimum_vocal_coverage_for_instrumental_edit,
        )
        if config.use_stems and instrumental_audio is not None:
            progress.log(
                f"Construction: intro {'instrumental stems' if intro_uses_stems else 'full mix'}, "
                f"outro {'instrumental stems' if outro_uses_stems else 'full mix'}"
            )
        edited = create_extended_edit(
            audio,
            None if selection.redrum_intro else intro,
            outro,
            config.crossfade_ms,
            instrumental_audio,
            selection.stem_reliability,
            config.minimum_stem_construction_reliability,
            config.minimum_vocal_coverage_for_instrumental_edit,
        )
        if config.insert_source_start is not None:
            assert config.insert_source_end is not None
            assert config.insert_destination is not None
            edited = insert_audio_region(
                edited,
                audio,
                config.insert_source_start,
                config.insert_source_end,
                config.insert_destination,
                config.insert_copies,
                max(config.crossfade_ms, 10.0),
            )
            progress.log(
                "Inserted custom source "
                f"{format_time(config.insert_source_start)}–"
                f"{format_time(config.insert_source_end)} at "
                f"{format_time(config.insert_destination)} "
                f"×{config.insert_copies}"
            )
        if selection.redrum_intro and intro is not None:
            assert selection.high_quality_drums is not None
            edited = create_redrum_intro(
                edited,
                audio,
                intro,
                selection.high_quality_drums,
                instrumental_audio,
            )
            progress.log("Redrum source: Demucs drums stem")
        return RenderStageResult(edited, intro_uses_stems, outro_uses_stems)

    def _export(
        self,
        source: Path,
        output: Path,
        analysis_stage: AnalysisStageResult,
        selection: SelectionStageResult,
        edited_audio: AudioData,
        progress: ProgressReporter,
    ) -> ExportStageResult:
        wav_output = output.parent.parent / WAV_OUTPUT_FOLDER_NAME / f"{source.stem}.wav"
        artifacts = self._export_service.export(
            ExportRequest(
                source,
                output,
                edited_audio,
                analysis_stage.audio,
                wav_output,
                analysis_stage.analysis,
                selection.intro,
                selection.outro,
                selection.config,
            ),
            progress,
        )
        return ExportStageResult(wav_output, artifacts)
