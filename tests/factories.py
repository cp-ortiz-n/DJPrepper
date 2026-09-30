"""Small, deterministic fixtures shared by unit tests."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from audioextender.analysis.section_selector import SectionCandidate


def candidate(**changes: Any) -> SectionCandidate:
    """Return a healthy candidate that a test can selectively modify."""
    base = SectionCandidate(
        start=4.0,
        end=8.0,
        score=0.8,
        rhythmic_strength=0.8,
        stability=0.8,
        transition_penalty=0.0,
        instrumentalness=0.8,
        seam_compatibility=0.9,
        harmonic_compatibility=0.9,
        bass_compatibility=0.9,
        timbre_compatibility=0.9,
        structure_consistency=0.8,
        context_compatibility=0.8,
        tail_release_compatibility=0.8,
        chord_return_compatibility=0.8,
        energy_context_match=0.8,
        boundary_grid_confidence=0.9,
        local_grid_confidence=0.9,
        arrangement_fit=0.5,
        energy_shape="stable",
        section_label="intro",
        unit_bars=4,
        repetitions=1,
    )
    return replace(base, **changes)
