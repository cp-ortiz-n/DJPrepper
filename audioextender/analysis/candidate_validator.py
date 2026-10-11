"""Final post-selection safety validation for intro and outro candidates."""

from __future__ import annotations

from dataclasses import dataclass, replace

from audioextender.analysis.section_selector import SectionCandidate
from audioextender.audio.loading import AudioData
from audioextender.core.config import EditConfig
from audioextender.processing.extended_edit import should_use_instrumental
from settings import (
    MINIMUM_FULL_MIX_INTRO_PERCUSSIVE_RATIO,
    MINIMUM_FULL_MIX_INTRO_RHYTHMIC_STRENGTH,
)


@dataclass(frozen=True)
class ValidationResult:
    candidate: SectionCandidate | None
    rejection_reason: str | None
    uses_instrumental: bool
    shortened: bool = False


class CandidateValidator:
    """Apply one consistent final safety policy to either side of an edit."""

    def validate(
        self,
        candidate: SectionCandidate | None,
        config: EditConfig,
        instrumental_audio: AudioData | None,
        stem_reliability: float,
        vocal_analysis_available: bool,
        position: str | None = None,
    ) -> ValidationResult:
        if candidate is None:
            return ValidationResult(None, None, False)

        uses_instrumental = should_use_instrumental(
            candidate,
            instrumental_audio,
            stem_reliability,
            config.minimum_stem_construction_reliability,
            config.minimum_vocal_coverage_for_instrumental_edit,
        )
        if config.manual_candidate_selection:
            selected = (
                replace(candidate, repetitions=config.maximum_repetitions)
                if candidate.repetitions > config.maximum_repetitions
                else candidate
            )
            return ValidationResult(
                selected,
                None,
                uses_instrumental,
                candidate.repetitions > config.maximum_repetitions,
            )
        if (
            vocal_analysis_available
            and not uses_instrumental
            and (
                candidate.vocal_coverage > config.maximum_vocal_coverage
                or candidate.vocal_boundary_risk > config.maximum_vocal_boundary_risk
            )
        ):
            return ValidationResult(
                None,
                f"vocals {candidate.vocal_coverage:.0%}, boundary risk {candidate.vocal_boundary_risk:.0%}",
                False,
            )
        if candidate.buildup_risk > config.maximum_buildup_risk:
            return ValidationResult(None, f"buildup risk {candidate.buildup_risk:.0%}", uses_instrumental)
        if candidate.bass_reset_risk > config.maximum_bass_reset_risk:
            return ValidationResult(None, f"bass-reset risk {candidate.bass_reset_risk:.0%}", uses_instrumental)
        if candidate.arrangement_fit < config.minimum_arrangement_fit:
            return ValidationResult(
                None,
                f"section {candidate.section_label}, arrangement fit {candidate.arrangement_fit:+.0%}",
                uses_instrumental,
            )
        if (
            position == "intro"
            and not uses_instrumental
            and candidate.rhythmic_strength < MINIMUM_FULL_MIX_INTRO_RHYTHMIC_STRENGTH
            and candidate.instrumentalness < MINIMUM_FULL_MIX_INTRO_PERCUSSIVE_RATIO
        ):
            return ValidationResult(
                None,
                f"exposed melodic phrase without a stable rhythmic bed (rhythm {candidate.rhythmic_strength:.0%})",
                False,
            )

        quality = candidate.instrumental_loop_quality if uses_instrumental else candidate.loop_quality
        quality_floor = max(
            config.minimum_loop_quality,
            config.minimum_intro_loop_quality if position == "intro" else config.minimum_outro_loop_quality,
        )
        if round(quality) < quality_floor:
            return ValidationResult(
                None,
                f"quality {quality:.0f}% below {quality_floor:.0f}%",
                uses_instrumental,
            )

        if candidate.repetitions > config.maximum_repetitions:
            return ValidationResult(
                replace(candidate, repetitions=config.maximum_repetitions),
                None,
                uses_instrumental,
                shortened=True,
            )
        return ValidationResult(candidate, None, uses_instrumental)
