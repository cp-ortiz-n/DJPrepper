"""Write completed edits, previews, auditions, and per-track cue sheets."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from audioextender.analysis.key_detection import TrackAnalysis
from audioextender.analysis.section_selector import SectionCandidate
from audioextender.audio.loading import AudioData, export_wav
from audioextender.core.config import EditConfig
from audioextender.core.defaults import EXTENDED_OUTPUT_FOLDER_NAME
from audioextender.core.exceptions import ExportError
from audioextender.core.interfaces import ProgressReporter
from audioextender.library.cue_export import CuePoint, build_cue_points, write_cue_sheet
from audioextender.processing.extended_edit import (
    create_extended_edit,
    create_splice_previews,
    optimize_candidate_boundaries,
)

AudioWriter = Callable[[AudioData, Path, int], None]
CueBuilder = Callable[..., tuple[CuePoint, ...]]
CueWriter = Callable[..., None]


@dataclass(frozen=True)
class ExportRequest:
    source: Path
    output: Path
    edited_audio: AudioData
    original_audio: AudioData
    wav_output: Path
    analysis: TrackAnalysis
    intro: SectionCandidate | None
    outro: SectionCandidate | None
    config: EditConfig


@dataclass(frozen=True)
class ExportResult:
    full_exported: bool
    intro_preview: Path | None = None
    outro_preview: Path | None = None
    cue_points: tuple[CuePoint, ...] = ()
    cue_sheet: Path | None = None


class ExportService:
    """Own all per-track output artifacts independently from analysis."""

    def __init__(
        self,
        audio_writer: AudioWriter = export_wav,
        cue_builder: CueBuilder = build_cue_points,
        cue_writer: CueWriter = write_cue_sheet,
    ) -> None:
        self._audio_writer = audio_writer
        self._cue_builder = cue_builder
        self._cue_writer = cue_writer

    @staticmethod
    def artifact_root(output: Path) -> Path:
        return output.parent.parent if output.parent.name == EXTENDED_OUTPUT_FOLDER_NAME else output.parent

    @staticmethod
    def preview_directory(source: Path, output: Path) -> Path:
        directory = ExportService.artifact_root(output) / "previews" / source.stem
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def export(self, request: ExportRequest, progress: ProgressReporter) -> ExportResult:
        intro_preview_path = None
        outro_preview_path = None
        cue_points: tuple[CuePoint, ...] = ()
        cue_sheet_path = None
        try:
            if request.config.create_previews:
                progress.update(94, "Creating splice previews")
                directory = self.preview_directory(request.source, request.output)
                intro_audio, outro_audio = create_splice_previews(
                    request.edited_audio,
                    request.intro,
                    request.outro,
                    request.config.crossfade_ms,
                    request.config.preview_seconds,
                )
                # A rebuilt track may now reject a side that previously had a
                # preview. Remove only that track's obsolete generated files so
                # the preview folder cannot advertise a splice the current WAV
                # and report no longer contain.
                if intro_audio is None:
                    (directory / "Intro Preview.wav").unlink(missing_ok=True)
                if outro_audio is None:
                    (directory / "Outro Preview.wav").unlink(missing_ok=True)
                if intro_audio is not None:
                    intro_preview_path = directory / "Intro Preview.wav"
                    self._audio_writer(intro_audio, intro_preview_path, request.config.pcm_bits)
                    progress.log(f"Intro preview: {intro_preview_path}")
                if outro_audio is not None:
                    outro_preview_path = directory / "Outro Preview.wav"
                    self._audio_writer(outro_audio, outro_preview_path, request.config.pcm_bits)
                    progress.log(f"Outro preview: {outro_preview_path}")

            if not request.config.preview_only:
                progress.update(96, "Exporting source WAV")
                self._audio_writer(
                    request.original_audio,
                    request.wav_output,
                    request.config.pcm_bits,
                )
                progress.log(f"Source WAV: {request.wav_output}")
                progress.update(98, "Exporting extended WAV")
                self._audio_writer(request.edited_audio, request.output, request.config.pcm_bits)
                progress.log(f"Export complete: {request.output}")
            else:
                progress.log("Preview-only mode: full extended WAV not written")

            if request.config.export_cues and not request.config.preview_only:
                cue_points = self._cue_builder(
                    request.analysis,
                    request.intro,
                    request.outro,
                    request.config.crossfade_ms,
                    request.edited_audio.duration,
                )
                if request.config.insert_source_start is not None:
                    assert request.config.insert_source_end is not None
                    assert request.config.insert_destination is not None
                    raw_added = (
                        request.config.insert_source_end - request.config.insert_source_start
                    ) * request.config.insert_copies
                    fade = max(request.config.crossfade_ms, 10.0) / 1000.0
                    joins = request.config.insert_copies + 1
                    added = max(0.0, raw_added - joins * fade)
                    destination = request.config.insert_destination
                    shifted = tuple(
                        replace(
                            cue,
                            start=cue.start + added,
                            end=cue.end + added if cue.end is not None else None,
                        )
                        if cue.start >= destination
                        else cue
                        for cue in cue_points
                    )
                    cue_points = tuple(
                        sorted(
                            (
                                *shifted,
                                CuePoint(
                                    "Inserted Section",
                                    destination,
                                    destination + added,
                                    kind="loop",
                                    purpose="Custom arrangement insertion",
                                ),
                            ),
                            key=lambda cue: cue.start,
                        )
                    )
                cue_sheet_path = self.artifact_root(request.output) / "cue_sheets" / f"{request.output.stem}.json"
                self._cue_writer(
                    cue_sheet_path,
                    request.source,
                    request.output,
                    self._metadata(request),
                    cue_points,
                )
                progress.log(f"Cue sheet: {cue_sheet_path}")
        except (OSError, RuntimeError, ValueError) as error:
            raise ExportError(f"Could not export {request.output.name}: {error}") from error

        progress.complete("Export complete")
        return ExportResult(
            full_exported=not request.config.preview_only,
            intro_preview=intro_preview_path,
            outro_preview=outro_preview_path,
            cue_points=cue_points,
            cue_sheet=cue_sheet_path,
        )

    def export_candidate_auditions(
        self,
        audio: AudioData,
        candidates: list[SectionCandidate],
        position: str,
        source: Path,
        output: Path,
        config: EditConfig,
        progress: ProgressReporter,
        instrumental_audio: AudioData | None = None,
        stem_reliability: float = 0.0,
    ) -> None:
        progress.update(82, f"Creating {position} candidate previews")
        directory = self.preview_directory(source, output)
        try:
            for rank, raw_candidate in enumerate(candidates, start=1):
                candidate = optimize_candidate_boundaries(audio, raw_candidate)
                edited = create_extended_edit(
                    audio,
                    candidate if position == "intro" else None,
                    candidate if position == "outro" else None,
                    config.crossfade_ms,
                    instrumental_audio,
                    stem_reliability,
                    config.minimum_stem_construction_reliability,
                    config.minimum_vocal_coverage_for_instrumental_edit,
                )
                intro_preview, outro_preview = create_splice_previews(
                    edited,
                    candidate if position == "intro" else None,
                    candidate if position == "outro" else None,
                    config.crossfade_ms,
                    config.preview_seconds,
                )
                preview = intro_preview if position == "intro" else outro_preview
                if preview is None:
                    continue
                path = directory / f"{position.title()} Candidate {rank}.wav"
                self._audio_writer(preview, path, config.pcm_bits)
                progress.log(f"Candidate audition {rank}: {path}")
        except (OSError, RuntimeError, ValueError) as error:
            raise ExportError(f"Could not export {position} candidate auditions: {error}") from error

    @staticmethod
    def _metadata(request: ExportRequest) -> dict[str, object]:
        analysis = request.analysis
        key_candidates = getattr(analysis, "key_candidates", ())
        if not isinstance(key_candidates, (list, tuple)):
            key_candidates = ()
        return {
            "duration_seconds": request.edited_audio.duration,
            "bpm": analysis.bpm,
            "key": analysis.key_label,
            "key_confidence": analysis.key_confidence / 100.0,
            "key_candidates": list(key_candidates),
            "beat_grid_confidence": analysis.beat_grid_confidence / 100.0,
            "downbeat_continuity": analysis.downbeat_continuity / 100.0,
            "groove": analysis.groove_label,
            "timing": analysis.timing_label,
        }
