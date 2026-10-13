"""Typed boundaries for the single-track processing transaction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from audioextender.analysis.dj_readiness import DJReadiness
from audioextender.analysis.key_detection import TrackAnalysis
from audioextender.analysis.section_selector import SectionCandidate
from audioextender.analysis.selection_coordinator import SideSelectionResult
from audioextender.audio.loading import AudioData
from audioextender.audio.redrum import redrum_added_seconds
from audioextender.core.config import EditConfig
from audioextender.core.models import FileResult, TrackArrangementSection, TrackSectionProfile
from audioextender.infrastructure.cache import AnalysisCache
from audioextender.library.export_service import ExportResult
from audioextender.processing.extended_edit import adaptive_crossfade_ms
from settings import DJ_READY_MINIMUM_BARS


@dataclass(frozen=True)
class AnalysisStageResult:
    """Facts produced by loading, analysis, stems, style, and readiness."""

    audio: AudioData
    analysis: TrackAnalysis
    cache: AnalysisCache
    config: EditConfig
    analysis_cache_hit: bool
    vocal_energy: np.ndarray | None
    instrumental_audio: AudioData | None
    drums_audio: AudioData | None
    stem_reliability: float
    vocal_cache_hit: bool
    intro_before: float | None
    outro_after: float | None
    automatic_intro_boundary: bool
    automatic_outro_boundary: bool
    detected_style: str | None
    preset_reason: str | None
    section_profiles: tuple[TrackSectionProfile, ...]
    readiness: DJReadiness
    stage_timings: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class SelectionStageResult:
    """Validated intro/outro decisions and construction inputs."""

    config: EditConfig
    intro: SectionCandidate | None
    outro: SectionCandidate | None
    intro_selection: SideSelectionResult
    outro_selection: SideSelectionResult
    reviews: dict[str, tuple[str | None, str | None]]
    intro_before: float | None
    outro_after: float | None
    outro_before: float | None
    automatic_intro_boundary: bool
    automatic_outro_boundary: bool
    intro_candidate_rank: int | None
    outro_candidate_rank: int | None
    intro_rejection_reason: str | None
    outro_rejection_reason: str | None
    intro_fallback: str | None
    outro_fallback: str | None
    intro_already_ready: bool
    outro_already_ready: bool
    redrum_intro: bool
    high_quality_drums: AudioData | None
    instrumental_audio: AudioData | None
    stem_reliability: float
    vocal_cache_hit: bool


@dataclass(frozen=True)
class RenderStageResult:
    """Rendered audio plus the construction choices reported to the user."""

    edited_audio: AudioData
    intro_uses_stems: bool
    outro_uses_stems: bool


@dataclass(frozen=True)
class ExportStageResult:
    """Export artifacts with the stable WAV destination used by FileResult."""

    wav_output: Path
    artifacts: ExportResult


def arrangement_sections(analysis: TrackAnalysis) -> tuple[TrackArrangementSection, ...]:
    """Merge adjacent bar labels into readable timeline regions."""
    labels = analysis.bar_section_labels
    confidence = analysis.bar_section_confidence
    boundaries = analysis.bar_boundaries
    usable = min(len(labels), len(confidence), max(0, len(boundaries) - 1))
    if usable == 0:
        return ()
    sections: list[TrackArrangementSection] = []
    first = 0
    for index in range(1, usable + 1):
        if index < usable and labels[index] == labels[first]:
            continue
        sections.append(
            TrackArrangementSection(
                float(boundaries[first]),
                float(boundaries[index]),
                str(labels[first]),
                sum(float(value) for value in confidence[first:index]) / (index - first),
            )
        )
        first = index
    return tuple(sections)


def assemble_analysis_result(
    source: Path,
    started: float,
    stage: AnalysisStageResult,
    clock: Callable[[], float],
) -> FileResult:
    """Build the analysis-only public result without rendering artifacts."""
    elapsed = clock() - started
    readiness = stage.readiness
    analysis = stage.analysis
    return FileResult(
        source_name=source.name,
        output=source,
        wav_output=source,
        elapsed=elapsed,
        bpm=analysis.bpm,
        tempo_drift_percent=analysis.tempo_drift_percent,
        beat_grid_confidence=analysis.beat_grid_confidence,
        key_label=analysis.key_label,
        key_confidence=analysis.key_confidence,
        key_candidates=analysis.key_candidates,
        groove_label=analysis.groove_label,
        swing_ratio=analysis.swing_ratio,
        timing_label=analysis.timing_label,
        downbeat_continuity=analysis.downbeat_continuity,
        beats=len(analysis.beat_times),
        bars=len(analysis.downbeat_indices),
        intro=None,
        outro=None,
        mix_in=None,
        mix_out=None,
        intro_existing_mix_bars=readiness.intro.mixable_bars,
        outro_existing_mix_bars=readiness.outro.mixable_bars,
        intro_already_dj_ready=(readiness.intro.mixable_bars >= DJ_READY_MINIMUM_BARS),
        outro_already_dj_ready=(readiness.outro.mixable_bars >= DJ_READY_MINIMUM_BARS),
        analysis_cache_hit=stage.analysis_cache_hit,
        vocal_cache_hit=stage.vocal_cache_hit,
        preset_name=stage.config.preset_name,
        detected_style=stage.detected_style,
        preset_reason=stage.preset_reason,
        stem_reliability=(stage.stem_reliability if stage.config.use_stems else None),
        output_duration=stage.audio.duration,
        section_profiles=stage.section_profiles,
        arrangement_sections=arrangement_sections(analysis),
        stage_timings=stage.stage_timings + (("Total", elapsed),),
    )


def assemble_file_result(
    source: Path,
    output: Path,
    started: float,
    analysis_stage: AnalysisStageResult,
    selection: SelectionStageResult,
    render: RenderStageResult,
    exported: ExportStageResult,
    clock: Callable[[], float],
) -> FileResult:
    """Assemble the stable public result from typed stage outputs."""
    intro = selection.intro
    outro = selection.outro
    config = selection.config
    intro_added = 0.0
    intro_output_start = None
    intro_output_end = None
    if intro is not None:
        unit = intro.end - intro.start
        if selection.redrum_intro:
            intro_added = redrum_added_seconds(intro)
            intro_output_start = 0.0
            intro_output_end = intro_added
        else:
            fade = adaptive_crossfade_ms(intro, config.crossfade_ms) / 1000.0
            intro_added = intro.repetitions * max(0.0, unit - fade)
            intro_output_start = intro.start
            intro_output_end = intro.start + intro_added
    outro_output_start = None
    outro_output_end = None
    if outro is not None:
        fade = adaptive_crossfade_ms(outro, config.crossfade_ms) / 1000.0
        unit = max(0.0, outro.end - outro.start - fade)
        outro_output_start = outro.end + intro_added - fade
        outro_output_end = outro_output_start + outro.repetitions * unit
    elapsed = clock() - started
    analysis = analysis_stage.analysis
    artifacts = exported.artifacts
    return FileResult(
        source_name=source.name,
        output=output,
        wav_output=exported.wav_output,
        intro_candidates=selection.intro_selection.options,
        outro_candidates=selection.outro_selection.options,
        intro_review_reason=selection.reviews.get("intro", (None, None))[0],
        intro_review_notes=selection.reviews.get("intro", (None, None))[1],
        outro_review_reason=selection.reviews.get("outro", (None, None))[0],
        outro_review_notes=selection.reviews.get("outro", (None, None))[1],
        elapsed=elapsed,
        bpm=analysis.bpm,
        tempo_drift_percent=analysis.tempo_drift_percent,
        beat_grid_confidence=analysis.beat_grid_confidence,
        key_label=analysis.key_label,
        key_confidence=analysis.key_confidence,
        key_candidates=analysis.key_candidates,
        groove_label=analysis.groove_label,
        swing_ratio=analysis.swing_ratio,
        timing_label=analysis.timing_label,
        downbeat_continuity=analysis.downbeat_continuity,
        beats=len(analysis.beat_times),
        bars=len(analysis.downbeat_indices),
        intro=intro,
        outro=outro,
        mix_in=0.0 if selection.redrum_intro else (intro.start if intro is not None else None),
        mix_out=(
            outro.start
            + (
                redrum_added_seconds(intro)
                if selection.redrum_intro
                else intro.repetitions
                * ((intro.end - intro.start) - adaptive_crossfade_ms(intro, config.crossfade_ms) / 1000.0)
            )
            if intro is not None and outro is not None
            else (outro.start if outro is not None else None)
        ),
        intro_output_start=intro_output_start,
        intro_output_end=intro_output_end,
        outro_output_start=outro_output_start,
        outro_output_end=outro_output_end,
        intro_before=selection.intro_before,
        outro_after=selection.outro_after,
        outro_before=selection.outro_before,
        automatic_intro_boundary=selection.automatic_intro_boundary,
        automatic_outro_boundary=selection.automatic_outro_boundary,
        preset_name=config.preset_name,
        detected_style=analysis_stage.detected_style,
        preset_reason=analysis_stage.preset_reason,
        intro_existing_mix_bars=analysis_stage.readiness.intro.mixable_bars,
        outro_existing_mix_bars=analysis_stage.readiness.outro.mixable_bars,
        intro_already_dj_ready=selection.intro_already_ready,
        outro_already_dj_ready=selection.outro_already_ready,
        analysis_cache_hit=analysis_stage.analysis_cache_hit,
        vocal_cache_hit=selection.vocal_cache_hit,
        intro_preview=artifacts.intro_preview,
        outro_preview=artifacts.outro_preview,
        full_exported=artifacts.full_exported,
        intro_candidate_rank=selection.intro_candidate_rank,
        outro_candidate_rank=selection.outro_candidate_rank,
        automatic_intro_length=(config.auto_select_bar_lengths and not config.intro_bars_locked),
        automatic_outro_length=(config.auto_select_bar_lengths and not config.outro_bars_locked),
        intro_rejection_reason=selection.intro_rejection_reason,
        outro_rejection_reason=selection.outro_rejection_reason,
        intro_fallback=selection.intro_fallback,
        outro_fallback=selection.outro_fallback,
        stem_reliability=(selection.stem_reliability if config.use_stems or selection.redrum_intro else None),
        intro_construction=(
            "progressive Demucs redrum"
            if selection.redrum_intro
            else "instrumental stems"
            if render.intro_uses_stems
            else "full mix"
        ),
        outro_construction=("instrumental stems" if render.outro_uses_stems else "full mix"),
        output_duration=render.edited_audio.duration,
        cue_points=artifacts.cue_points,
        cue_sheet=artifacts.cue_sheet,
        section_profiles=analysis_stage.section_profiles,
        arrangement_sections=arrangement_sections(analysis),
        stage_timings=analysis_stage.stage_timings + (("Total", clock() - started),),
    )
