"""Reusable candidate-ranking policy for intro and outro selection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np

from audioextender.analysis.key_detection import TrackAnalysis
from audioextender.analysis.section_selector import SectionCandidate, rank_sections
from audioextender.core.defaults import AUTO_BAR_MAXIMUM_QUALITY_LOSS, SUPPORTED_BAR_COUNTS
from audioextender.core.exceptions import CandidateSelectionError

Position = Literal["intro", "outro"]
Ranker = Callable[..., list[SectionCandidate]]


@dataclass(frozen=True)
class SelectionRequest:
    """Everything needed to rank one side of an extended edit."""

    position: Position
    maximum_bars: int
    duration: float
    search_seconds: float
    maximum_end: float | None = None
    minimum_start: float | None = None
    count: int = 3
    automatic_length: bool = True


@dataclass(frozen=True)
class RankedSelection:
    candidates: tuple[SectionCandidate, ...]
    bars: int
    reason: str | None = None


class CandidateSelectionService:
    """Rank musical candidates independently from CLI and rendering concerns."""

    def __init__(self, ranker: Ranker = rank_sections) -> None:
        self._ranker = ranker

    def rank(
        self,
        analysis: TrackAnalysis,
        request: SelectionRequest,
        vocal_energy: np.ndarray | None = None,
    ) -> RankedSelection:
        """Rank the strongest candidate set for the requested intro or outro."""
        if not request.automatic_length:
            candidates = self._rank_at_length(analysis, request, request.maximum_bars, vocal_energy)
            return RankedSelection(tuple(candidates), request.maximum_bars)

        lengths = [bars for bars in SUPPORTED_BAR_COUNTS if 0 < bars <= request.maximum_bars]
        ranked: dict[int, list[SectionCandidate]] = {}
        for bars in lengths:
            try:
                ranked[bars] = self._rank_at_length(analysis, request, bars, vocal_energy)
            except RuntimeError:
                continue
        if not ranked:
            raise CandidateSelectionError(
                f"No loop-able {request.position} phrase exists up to {request.maximum_bars} bars"
            )

        shortest_quality = ranked[min(ranked)][0].loop_quality
        scored = [
            (self._length_fitness(candidate, bars, shortest_quality), bars, candidate)
            for bars, candidates in ranked.items()
            for candidate in candidates[:1]
        ]
        _, chosen_bars, chosen = max(scored, key=lambda item: item[0])
        reason = (
            f"quality {chosen.loop_quality:.0f}%, {chosen.energy_shape} energy, "
            f"rhythm {chosen.rhythmic_strength:.0%}, instrumental "
            f"{chosen.instrumentalness:.0%}"
        )
        return RankedSelection(tuple(ranked[chosen_bars]), chosen_bars, reason)

    def _rank_at_length(
        self,
        analysis: TrackAnalysis,
        request: SelectionRequest,
        bars: int,
        vocal_energy: np.ndarray | None,
    ) -> list[SectionCandidate]:
        return self._ranker(
            analysis,
            bars,
            request.position,
            request.duration,
            request.search_seconds,
            vocal_energy,
            request.maximum_end,
            request.minimum_start,
            count=request.count,
        )

    @staticmethod
    def _length_fitness(candidate: SectionCandidate, bars: int, shortest_quality: float) -> float:
        fitness = (
            0.50 * candidate.loop_quality / 100.0
            + 0.18 * candidate.structure_consistency
            + 0.14 * candidate.energy_context_match
            + 0.10 * candidate.stability
            + 0.08 * candidate.instrumentalness
            + 0.12 * candidate.chord_return_compatibility
            + 0.10 * candidate.boundary_grid_confidence
            - 0.16 * candidate.buildup_risk
            - 0.14 * candidate.bass_reset_risk
            - 0.22 * candidate.harmonic_resolution_risk
        )
        if bars == 2:
            fitness -= 0.06
        elif bars == 8:
            fitness += (
                0.035
                if (
                    candidate.rhythmic_strength >= 0.42
                    and candidate.instrumentalness >= 0.48
                    and candidate.energy_shape == "stable"
                )
                else -0.045
            )
        elif bars >= 16:
            fitness += (
                0.025
                if (
                    candidate.rhythmic_strength >= 0.55
                    and candidate.instrumentalness >= 0.55
                    and candidate.energy_shape == "stable"
                )
                else -0.12
            )
        if bars > 4 and candidate.loop_quality < (shortest_quality - AUTO_BAR_MAXIMUM_QUALITY_LOSS):
            fitness -= 0.10
        return fitness
