"""Coordinate candidate ranking, protected boundaries, choices, and fallbacks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from helpers.analysis import TrackAnalysis
from helpers.candidate_reranker import rerank_candidates
from helpers.candidate_selection import (
    CandidateRankingService,
    Position,
    SelectionRequest,
)
from helpers.candidate_validator import CandidateValidator, ValidationResult
from helpers.audio_loader import AudioData
from helpers.config import EditConfig
from helpers.interfaces import ProgressReporter
from helpers.section_selector import SectionCandidate
from helpers.splice_policy import SplicePlan, build_splice_plan
from settings import SUPPORTED_BAR_COUNTS

CandidateChooser = Callable[
    [list[SectionCandidate], Position, int],
    tuple[SectionCandidate | None, int | None],
]
CandidateReranker = Callable[
    [list[SectionCandidate], Position, str | None],
    list[SectionCandidate],
]
SplicePlanner = Callable[[SectionCandidate, float], SplicePlan]


@dataclass(frozen=True)
class SideSelectionRequest:
    position: Position
    bars: int
    bars_locked: bool
    search_seconds: float
    requested_rank: int
    count: int = 3
    maximum_end: float | None = None
    minimum_start: float | None = None
    automatic_boundary: bool = False


@dataclass(frozen=True)
class SideSelectionResult:
    candidate: SectionCandidate | None
    rank: int | None
    options: tuple[SectionCandidate, ...]
    maximum_end: float | None
    minimum_start: float | None
    automatic_boundary: bool
    automatic_length: bool
    fallback: str | None = None


@dataclass(frozen=True)
class FinalizedSelection:
    """Validated selection plus rendering policy, produced by orchestration."""

    validation: ValidationResult
    splice_plan: SplicePlan | None

    @property
    def candidate(self) -> SectionCandidate | None:
        return self.validation.candidate

    @property
    def rejection_reason(self) -> str | None:
        return self.validation.rejection_reason

    @property
    def uses_instrumental(self) -> bool:
        return self.validation.uses_instrumental

    @property
    def shortened(self) -> bool:
        return self.validation.shortened


def candidate_safety_issue(
    candidate: SectionCandidate,
    config: EditConfig,
    position: Position | None = None,
) -> str | None:
    return CandidateValidator().safety_issue(
        candidate,
        config,
        position,
        vocal_analysis_available=candidate.vocal_energy is not None,
    )


class SelectionCoordinator:
    """Apply identical selection behavior to either side of an edit."""

    def __init__(
        self,
        ranking: CandidateRankingService | None = None,
        validator: CandidateValidator | None = None,
        reranker: CandidateReranker = rerank_candidates,
        splice_planner: SplicePlanner = build_splice_plan,
    ) -> None:
        self._ranking = ranking or CandidateRankingService()
        self._validator = validator or CandidateValidator()
        self._reranker = reranker
        self._splice_planner = splice_planner

    def finalize(
        self,
        candidate: SectionCandidate | None,
        config: EditConfig,
        instrumental_audio: AudioData | None,
        stem_reliability: float,
        vocal_analysis_available: bool,
        position: Position,
    ) -> FinalizedSelection:
        """Complete selection with the authoritative post-boundary validation."""
        validation = self._validator.validate(
            candidate,
            config,
            instrumental_audio,
            stem_reliability,
            vocal_analysis_available,
            position=position,
        )
        plan = (
            self._splice_planner(validation.candidate, config.crossfade_ms)
            if validation.candidate is not None
            else None
        )
        return FinalizedSelection(validation, plan)

    def select(
        self,
        analysis: TrackAnalysis,
        duration: float,
        vocal_energy: np.ndarray | None,
        config: EditConfig,
        request: SideSelectionRequest,
        chooser: CandidateChooser,
        progress: ProgressReporter,
        prefer_instrumental: bool = False,
    ) -> SideSelectionResult:
        if request.bars == 0:
            return SideSelectionResult(
                None, None, (), None, None, False, False
            )

        maximum_end = request.maximum_end
        minimum_start = request.minimum_start
        automatic_boundary = request.automatic_boundary
        automatic_length = config.auto_select_bar_lengths and not request.bars_locked

        try:
            ranked = self._rank(
                analysis, duration, vocal_energy, request, maximum_end,
                minimum_start, automatic_length,
            )
        except RuntimeError:
            if not automatic_boundary:
                if request.position == "intro" and maximum_end is not None:
                    progress.log(
                        "Protected opening contains no complete full-mix phrase; "
                        "leaving intro selection available for percussion fallback"
                    )
                    return SideSelectionResult(
                        None, None, (), maximum_end, minimum_start,
                        False, automatic_length,
                        "no complete full-mix phrase before protected boundary",
                    )
                raise
            boundary_name = "vocal entrance" if request.position == "intro" else "vocal release"
            progress.log(
                f"Automatic {boundary_name} left no complete loop; using normal "
                f"{request.position} search"
            )
            if request.position == "intro":
                maximum_end = None
            else:
                minimum_start = None
            automatic_boundary = False
            ranked = self._rank(
                analysis, duration, vocal_energy, request, maximum_end,
                minimum_start, automatic_length,
            )

        if ranked.reason:
            progress.log(
                f"Automatic {request.position} length: {ranked.bars} bars "
                f"({ranked.reason})"
            )
        options = self._prefer_instrumental(list(ranked.candidates), prefer_instrumental)
        options = self._reranker(options, request.position, config.preset_name)
        chosen, rank = chooser(options, request.position, request.requested_rank)
        fallback_description = None

        if (
            chosen is not None
            and not config.choose_candidates
            and not config.manual_candidate_selection
            and request.requested_rank == 1
            and (
                issue := self._validator.safety_issue(
                    chosen,
                    config,
                    request.position,
                    vocal_analysis_available=vocal_energy is not None,
                )
            ) is not None
        ):
            fallback = self._safe_fallback(
                chosen, options, analysis, duration, vocal_energy, config,
                request, maximum_end, minimum_start, automatic_length,
            )
            if fallback is not None:
                chosen, rank, description = fallback
                fallback_description = f"rejected {issue}; {description}"
                progress.log(
                    f"{request.position.title()} fallback: {fallback_description}"
                )

        return SideSelectionResult(
            chosen, rank, tuple(options), maximum_end, minimum_start,
            automatic_boundary, automatic_length, fallback_description,
        )

    def _rank(
        self,
        analysis: TrackAnalysis,
        duration: float,
        vocal_energy: np.ndarray | None,
        request: SideSelectionRequest,
        maximum_end: float | None,
        minimum_start: float | None,
        automatic_length: bool,
    ):
        return self._ranking.rank(
            analysis,
            SelectionRequest(
                position=request.position,
                maximum_bars=request.bars,
                duration=duration,
                search_seconds=request.search_seconds,
                maximum_end=maximum_end,
                minimum_start=minimum_start,
                count=request.count,
                automatic_length=automatic_length,
            ),
            vocal_energy,
        )

    @staticmethod
    def _prefer_instrumental(
        candidates: list[SectionCandidate], enabled: bool
    ) -> list[SectionCandidate]:
        if not enabled:
            return candidates
        return sorted(
            candidates,
            key=lambda candidate: (
                candidate.score
                + 0.30 * min(max(candidate.vocal_energy or 0.0, 0.0), 1.0)
                + 0.72 * candidate.vocal_phrase_penalty
                + 0.85 * candidate.vocal_boundary_risk
                + 0.004 * candidate.instrumental_loop_quality
            ),
            reverse=True,
        )

    def _safe_fallback(
        self,
        original: SectionCandidate,
        options: list[SectionCandidate],
        analysis: TrackAnalysis,
        duration: float,
        vocal_energy: np.ndarray | None,
        config: EditConfig,
        request: SideSelectionRequest,
        maximum_end: float | None,
        minimum_start: float | None,
        allow_shorter: bool,
    ) -> tuple[SectionCandidate, int | None, str] | None:
        def safe(candidate: SectionCandidate) -> bool:
            return (
                self._validator.safety_issue(
                    candidate,
                    config,
                    request.position,
                    vocal_analysis_available=vocal_energy is not None,
                ) is None
                and candidate.loop_quality >= config.minimum_fallback_loop_quality
            )

        for rank, candidate in enumerate(options, start=1):
            if candidate is not original and safe(candidate):
                return candidate, rank, f"alternate candidate {rank} at the same length"
        if not allow_shorter:
            return None
        original_bars = original.unit_bars * original.repetitions
        for bars in sorted(
            (value for value in SUPPORTED_BAR_COUNTS if 0 < value < original_bars),
            reverse=True,
        ):
            shorter = SideSelectionRequest(
                position=request.position,
                bars=bars,
                bars_locked=True,
                search_seconds=request.search_seconds,
                requested_rank=1,
                maximum_end=maximum_end,
                minimum_start=minimum_start,
            )
            try:
                ranked = self._rank(
                    analysis, duration, vocal_energy, shorter, maximum_end,
                    minimum_start, False,
                )
            except RuntimeError:
                continue
            for candidate in ranked.candidates:
                if safe(candidate):
                    return candidate, None, f"shortened from {original_bars} to {bars} bars"
        return None
