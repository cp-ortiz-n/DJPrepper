"""Style-aware second-stage ranking and explainable candidate checks."""

from __future__ import annotations

from dataclasses import dataclass

from audioextender.analysis.candidate_selection import Position
from audioextender.analysis.section_selector import SectionCandidate


@dataclass(frozen=True)
class CandidateAssessment:
    """Assessment of a candidate section with per-factor metrics and warnings."""

    phrase: float
    loop: float
    transition: float
    rerank_score: float
    warnings: tuple[str, ...]


def assess_candidate(
    candidate: SectionCandidate,
    position: Position,
    style: str | None,
) -> CandidateAssessment:
    """Score distinct musical questions instead of hiding them in one number."""
    phrase = candidate.phrase_suitability
    loop = candidate.loop_quality
    transition = candidate.transition_quality
    label = (style or "").casefold()
    if "slow" in label or "vocal" in label or "subtle" in label:
        weights = (0.40, 0.24, 0.36)
    elif "club" in label or "rhythm" in label:
        weights = (0.25, 0.42, 0.33)
    else:
        weights = (0.33, 0.34, 0.33)
    score = weights[0] * phrase + weights[1] * loop + weights[2] * transition
    if position == "intro" and candidate.section_label != "intro":
        score -= 5.0
    if position == "outro" and candidate.section_label not in {"closing", "fade"}:
        score -= 3.0
    score += 8.0 * candidate.regional_compatibility
    score -= 12.0 * candidate.regional_boundary_risk

    warnings: list[str] = []
    if candidate.buildup_risk >= 0.45:
        warnings.append("buildup may reset")
    if candidate.bass_reset_risk >= 0.40:
        warnings.append("bass may disappear at repeat")
    if candidate.harmonic_resolution_risk >= 0.45:
        warnings.append("chord progression may be interrupted")
    if candidate.vocal_boundary_risk >= 0.35:
        warnings.append("vocal pickup near splice")
    if candidate.boundary_grid_confidence < 0.55:
        warnings.append("uncertain beat boundary")
    if transition < 60.0:
        warnings.append("weak transition context")
    if candidate.regional_boundary_risk >= 0.35:
        warnings.append("crosses or conflicts with a musical region")
    return CandidateAssessment(phrase, loop, transition, score, tuple(warnings))


def rerank_candidates(
    candidates: list[SectionCandidate],
    position: Position,
    style: str | None,
) -> list[SectionCandidate]:
    """Rerank generated candidates without changing or fabricating candidates."""
    return sorted(
        candidates,
        key=lambda item: assess_candidate(item, position, style).rerank_score,
        reverse=True,
    )
