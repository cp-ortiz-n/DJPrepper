"""Immutable handoff models for the single-track processing transaction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from audioextender.analysis.dj_readiness import DJReadiness
from audioextender.analysis.key_detection import TrackAnalysis
from audioextender.analysis.section_selector import SectionCandidate
from audioextender.analysis.selection_coordinator import SideSelectionResult
from audioextender.audio.loading import AudioData
from audioextender.core.config import EditConfig
from audioextender.core.models import TrackArrangementSection, TrackSectionProfile
from audioextender.infrastructure.cache import AnalysisCache
from audioextender.library.export_service import ExportResult


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
