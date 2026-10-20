"""Configuration values for the extended-edit pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from audioextender.core.defaults import (
    ANALYSIS_HOP_LENGTH,
    BEATS_PER_BAR,
    DEFAULT_AUTO_BAR_SELECTION,
    DEFAULT_CANDIDATE_COUNT,
    DEFAULT_EXPORT_CUES,
    DEFAULT_INTRO_BARS,
    DEFAULT_MINIMUM_INTRO_LOOP_QUALITY,
    DEFAULT_MINIMUM_OUTRO_LOOP_QUALITY,
    DEFAULT_OUTRO_BARS,
    DEFAULT_PCM_BITS,
    DEFAULT_USE_STEMS,
    INTRO_SEARCH_SECONDS,
    MAXIMUM_BASS_RESET_RISK,
    MAXIMUM_BUILDUP_RISK,
    MAXIMUM_VOCAL_BOUNDARY_RISK,
    MAXIMUM_VOCAL_COVERAGE,
    MINIMUM_ARRANGEMENT_FIT,
    MINIMUM_CROSSFADE_MS,
    MINIMUM_FALLBACK_LOOP_QUALITY,
    MINIMUM_STEM_CONSTRUCTION_RELIABILITY,
    MINIMUM_VOCAL_COVERAGE_FOR_INSTRUMENTAL_EDIT,
    OUTRO_SEARCH_SECONDS,
    SUPPORTED_BAR_COUNTS,
    SUPPORTED_PCM_BITS,
)
from audioextender.core.exceptions import ConfigurationError


@dataclass(frozen=True)
class EditConfig:
    """User-facing and analysis settings for one edit."""

    intro_bars: int = DEFAULT_INTRO_BARS
    outro_bars: int = DEFAULT_OUTRO_BARS
    use_stems: bool = DEFAULT_USE_STEMS
    pcm_bits: int = DEFAULT_PCM_BITS
    beats_per_bar: int = BEATS_PER_BAR
    # Search windows intentionally overlap the middle for short/radio edits.
    intro_search_seconds: float = INTRO_SEARCH_SECONDS
    outro_search_seconds: float = OUTRO_SEARCH_SECONDS
    crossfade_ms: float = MINIMUM_CROSSFADE_MS
    analysis_hop_length: int = ANALYSIS_HOP_LENGTH
    minimum_loop_quality: float = 0.0
    minimum_intro_loop_quality: float = DEFAULT_MINIMUM_INTRO_LOOP_QUALITY
    minimum_outro_loop_quality: float = DEFAULT_MINIMUM_OUTRO_LOOP_QUALITY
    maximum_repetitions: int = 8
    preset_name: str | None = None
    intro_bars_locked: bool = False
    outro_bars_locked: bool = False
    stems_locked: bool = False
    maximum_vocal_coverage: float = MAXIMUM_VOCAL_COVERAGE
    maximum_vocal_boundary_risk: float = MAXIMUM_VOCAL_BOUNDARY_RISK
    maximum_buildup_risk: float = MAXIMUM_BUILDUP_RISK
    maximum_bass_reset_risk: float = MAXIMUM_BASS_RESET_RISK
    minimum_arrangement_fit: float = MINIMUM_ARRANGEMENT_FIT
    minimum_fallback_loop_quality: float = MINIMUM_FALLBACK_LOOP_QUALITY
    cache_directory: str = ""
    cache_enabled: bool = True
    refresh_cache: bool = False
    create_previews: bool = False
    create_candidate_auditions: bool = False
    preview_only: bool = False
    preview_seconds: float = 8.0
    candidate_count: int = DEFAULT_CANDIDATE_COUNT
    intro_candidate: int = 1
    outro_candidate: int = 1
    choose_candidates: bool = False
    review_mode: bool = False
    manual_candidate_selection: bool = False
    custom_intro_start: float | None = None
    custom_intro_end: float | None = None
    custom_intro_copies: int = 1
    custom_outro_start: float | None = None
    custom_outro_end: float | None = None
    custom_outro_copies: int = 1
    insert_source_start: float | None = None
    insert_source_end: float | None = None
    insert_destination: float | None = None
    insert_copies: int = 1
    auto_select_bar_lengths: bool = DEFAULT_AUTO_BAR_SELECTION
    minimum_stem_construction_reliability: float = MINIMUM_STEM_CONSTRUCTION_RELIABILITY
    minimum_vocal_coverage_for_instrumental_edit: float = MINIMUM_VOCAL_COVERAGE_FOR_INSTRUMENTAL_EDIT
    export_cues: bool = DEFAULT_EXPORT_CUES
    analysis_only: bool = False

    def validate(self) -> None:
        """Validate edit settings and raise for invalid values."""

        if self.intro_bars not in SUPPORTED_BAR_COUNTS:
            raise ConfigurationError(f"intro bars must be one of {SUPPORTED_BAR_COUNTS}")
        if self.outro_bars not in SUPPORTED_BAR_COUNTS:
            raise ConfigurationError(f"outro bars must be one of {SUPPORTED_BAR_COUNTS}")
        if self.pcm_bits not in SUPPORTED_PCM_BITS:
            raise ConfigurationError(f"PCM depth must be one of {SUPPORTED_PCM_BITS}")
        if self.preview_seconds <= 0:
            raise ConfigurationError("preview seconds must be greater than zero")
        if self.candidate_count < 1:
            raise ConfigurationError("candidate count must be at least one")
        if not 1 <= self.maximum_repetitions <= 8:
            raise ConfigurationError("maximum repetitions must be between 1 and 8")
        if not 1 <= self.crossfade_ms <= 100:
            raise ConfigurationError("cross fade must be between 1 and 100 ms")

        self._validate_custom_sections()
        self._validate_insertion()

    def _validate_custom_sections(self) -> None:
        """Validate optional custom intro and outro sections."""

        for position in ("intro", "outro"):
            start = getattr(self, f"custom_{position}_start")
            end = getattr(self, f"custom_{position}_end")
            copies = getattr(self, f"custom_{position}_copies")
            if (start is None) != (end is None):
                raise ConfigurationError(f"custom {position} requires both start and end")
            if start is not None and (start < 0 or end <= start):
                raise ConfigurationError(f"custom {position} must have start < end")
            if not 1 <= copies <= 8:
                raise ConfigurationError(f"custom {position} copies must be between 1 and 8")

    def _validate_insertion(self) -> None:
        """Validate optional section insertion settings."""

        insert_values = (
            self.insert_source_start,
            self.insert_source_end,
            self.insert_destination,
        )
        if any(value is not None for value in insert_values):
            if any(value is None for value in insert_values):
                raise ConfigurationError("section insertion requires source start, source end, and destination")
            assert self.insert_source_start is not None
            assert self.insert_source_end is not None
            assert self.insert_destination is not None
            if self.insert_source_start < 0 or self.insert_source_end <= self.insert_source_start:
                raise ConfigurationError("insert source must have start < end")
            if self.insert_destination < 0:
                raise ConfigurationError("insert destination cannot be negative")
        if not 1 <= self.insert_copies <= 8:
            raise ConfigurationError("insert copies must be between 1 and 8")
