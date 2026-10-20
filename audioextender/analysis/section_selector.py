"""Beat-aligned candidate generation and scoring."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

import numpy as np

from audioextender.analysis.key_detection import TrackAnalysis
from audioextender.analysis.section_context import (
    behavior_compatibility,
    broad_section_bounds,
    classify_interval,
)
from audioextender.analysis.selection_metrics import (
    _chord_transition_score,
    _coefficient_of_variation,
    _cosine_similarity,
    _means_by_bar,
    _normalized_slope,
    _vocal_phrase_metrics,
)
from audioextender.analysis.selection_models import SectionCandidate
from audioextender.core.defaults import (
    INTRO_IDENTITY_BARS,
    MINIMUM_OPENING_IDENTITY_QUALITY,
    MINIMUM_UNIQUE_STRUCTURE_MATCH,
    OPENING_IDENTITY_SCORE_TOLERANCE,
    PREFER_UNIQUE_MATERIAL,
    PREFERRED_LOOP_QUALITY_TARGET,
    PREFERRED_QUALITY_SCORE_TOLERANCE,
    UNIQUE_MATERIAL_QUALITY_TOLERANCE,
    UNIQUE_MATERIAL_SCORE_TOLERANCE,
)


def _choose_with_unique_material(
    options: list[SectionCandidate],
) -> SectionCandidate:
    """Prefer a musically competitive longer unit over mechanical repetition."""
    best = max(
        options,
        key=lambda candidate: candidate.score + 0.004 * candidate.loop_quality,
    )
    if not PREFER_UNIQUE_MATERIAL or best.repetitions <= 1:
        return best
    compatible_longer = [
        candidate
        for candidate in options
        if candidate.unit_bars > best.unit_bars
        and candidate.repetitions < best.repetitions
        and candidate.score >= best.score - UNIQUE_MATERIAL_SCORE_TOLERANCE
        and candidate.loop_quality >= best.loop_quality - UNIQUE_MATERIAL_QUALITY_TOLERANCE
        and candidate.structure_consistency >= MINIMUM_UNIQUE_STRUCTURE_MATCH
    ]
    if compatible_longer:
        return max(
            compatible_longer,
            key=lambda candidate: (
                candidate.unit_bars,
                candidate.score + 0.004 * candidate.loop_quality,
            ),
        )
    return best


def _rank_fixed_sections(
    analysis: TrackAnalysis,
    bars: int,
    position: Literal["intro", "outro"],
    duration: float,
    search_seconds: float,
    vocal_energy: np.ndarray | None = None,
    maximum_end: float | None = None,
    minimum_start: float | None = None,
) -> list[SectionCandidate]:
    """Score bar-aligned regions, stepping by four bars to preserve phrasing."""
    boundaries = analysis.bar_boundaries
    if len(boundaries) <= bars:
        raise RuntimeError(f"Track is too short to find a complete {bars}-bar section")
    broad_regions = broad_section_bounds(analysis)
    target_region = broad_regions[0] if position == "intro" else broad_regions[-1]
    target_behavior = classify_interval(analysis, target_region[1], target_region[2], vocal_energy)

    if position == "intro":
        # Define opening/closing zones in musical bars, not percentages of clock
        # time. This prevents a slow song from calling a stable first-verse groove
        # at 00:40–01:05 its "intro" merely because the track is long.
        zone_bars = max(16, bars)
        zone_end_index = min(zone_bars, len(boundaries) - 1)
        search_start = float(boundaries[0])
        search_end = min(float(boundaries[zone_end_index]), duration * 0.30, search_seconds, 90.0)
        if maximum_end is not None:
            search_end = min(search_end, maximum_end)
        latest_intro_start = float(boundaries[min(8, len(boundaries) - 1)])
    else:
        zone_bars = max(16, bars)
        if maximum_end is not None:
            # A DJ-supplied closing boundary re-anchors the outro search window
            # before that point instead of keeping it tied to the track's end.
            end_index = max(1, int(np.searchsorted(boundaries, maximum_end, side="right") - 1))
            zone_start_index = max(0, end_index - zone_bars)
            search_start = max(float(boundaries[zone_start_index]), maximum_end - search_seconds)
            search_end = maximum_end
        else:
            zone_start_index = max(0, len(boundaries) - zone_bars - 1)
            search_start = max(float(boundaries[zone_start_index]), duration * 0.60, duration - search_seconds)
            search_end = duration
        if minimum_start is not None:
            search_start = max(search_start, minimum_start)
        latest_intro_start = duration

    candidates: list[SectionCandidate] = []
    # Four-bar steps are a pragmatic phrase grid; candidates themselves remain
    # exact requested lengths and begin on inferred downbeats.
    for index in range(0, len(boundaries) - bars, 4):
        start, end = float(boundaries[index]), float(boundaries[index + bars])
        if start < search_start or end > search_end:
            continue
        if position == "intro" and start > latest_intro_start:
            continue
        mask = (analysis.frame_times >= start) & (analysis.frame_times < end)
        if np.count_nonzero(mask) < 8:
            continue

        rms = analysis.rms[mask]
        percussion = analysis.percussion_rms[mask]
        onset = analysis.onset[mask]
        flux = analysis.spectral_flux[mask]
        rhythmic = float(np.clip(np.mean(percussion), 0, 1))
        activity = float(np.clip(np.mean(onset), 0, 1))
        loudness = float(np.clip(np.mean(rms), 0, 1))
        section_labels = analysis.bar_section_labels[index : index + bars]
        section_confidences = analysis.bar_section_confidence[index : index + bars]
        votes: dict[str, float] = {}
        for label, confidence in zip(section_labels, section_confidences, strict=True):
            votes[str(label)] = votes.get(str(label), 0.0) + float(confidence)
        section_label = max(votes, key=lambda label: votes[label]) if votes else "unknown"
        section_confidence = votes.get(section_label, 0.0) / max(float(len(section_confidences)), 1.0) if votes else 0.0
        intro_fit = {
            "intro": 1.0,
            "verse": 0.25,
            "breakdown": 0.10,
            "closing": -0.45,
            "fade": -0.55,
            "chorus": -0.85,
            "drop": -1.0,
            "buildup": -1.0,
        }
        outro_fit = {
            "closing": 1.0,
            "fade": 0.65,
            "verse": 0.20,
            "breakdown": 0.10,
            "intro": -0.45,
            "chorus": -0.75,
            "drop": -0.90,
            "buildup": -1.0,
        }
        arrangement_fit = (intro_fit if position == "intro" else outro_fit).get(section_label, 0.0) * section_confidence
        grid_values = analysis.bar_grid_confidence[index : index + bars]
        local_grid_confidence = float(np.mean(grid_values)) if len(grid_values) else 0.0
        boundary_grid_confidence = float(min(grid_values[0], grid_values[-1])) if len(grid_values) else 0.0
        candidate_boundaries = boundaries[index : index + bars + 1]
        regional_beat_duration = (end - start) / max(bars * 4, 1)
        candidate_behavior = classify_interval(analysis, start, end, vocal_energy)
        regional_compatibility = (
            behavior_compatibility(candidate_behavior, target_behavior)
            if candidate_behavior is not None and target_behavior is not None
            else 0.5
        )
        crossed_region_boundary = any(
            start < boundary < end for boundary in (broad_regions[0][2], broad_regions[-1][1])
        )
        context_start = end if position == "intro" else max(0.0, start - 4 * regional_beat_duration)
        context_end = min(duration, end + 4 * regional_beat_duration) if position == "intro" else start
        context_behavior = classify_interval(analysis, context_start, context_end, vocal_energy)
        local_behavior_match = (
            behavior_compatibility(candidate_behavior, context_behavior)
            if candidate_behavior is not None and context_behavior is not None
            else 0.65
        )
        regional_boundary_risk = float(
            np.clip(
                0.65 * (1.0 if crossed_region_boundary else 0.0) + 0.35 * (1.0 - local_behavior_match),
                0.0,
                1.0,
            )
        )
        bar_rms = _means_by_bar(analysis.rms, analysis.frame_times, candidate_boundaries)
        bar_centroid = _means_by_bar(analysis.spectral_centroid, analysis.frame_times, candidate_boundaries)
        bar_bass = _means_by_bar(analysis.bass_rms, analysis.frame_times, candidate_boundaries)
        stability = float(
            np.exp(-1.6 * (_coefficient_of_variation(bar_rms) + 0.35 * _coefficient_of_variation(bar_centroid)))
        )

        # HPSS is not a vocal detector, but harmonic-dominant regions are more
        # likely to contain vocals, leads, or a chorus. Favor percussion that is
        # strong relative to the complete mix when Demucs is unavailable.
        percussion_ratio = np.clip(percussion / (rms + 1e-5), 0.0, 1.0)
        instrumentalness = float(np.mean(percussion_ratio))

        beat_duration = (end - start) / max(bars * 4, 1)
        vocal_coverage = 0.0
        vocal_boundary_risk = 0.0
        vocal_phrase_penalty = 0.0
        if vocal_energy is not None:
            (
                vocal_coverage,
                vocal_boundary_risk,
                vocal_phrase_penalty,
            ) = _vocal_phrase_metrics(
                vocal_energy,
                analysis.frame_times,
                start,
                end,
                beat_duration,
            )
        first_edge = (analysis.frame_times >= start) & (analysis.frame_times < start + beat_duration)
        last_edge = (analysis.frame_times >= end - beat_duration) & (analysis.frame_times < end)

        def edge_similarity(
            values: np.ndarray,
            first_mask: np.ndarray = first_edge,
            last_mask: np.ndarray = last_edge,
        ) -> float:
            first = float(np.mean(values[first_mask]))
            last = float(np.mean(values[last_mask]))
            scale = max(first, last, 0.08)
            return float(np.exp(-abs(first - last) / scale))

        energy_compatibility = edge_similarity(analysis.rms)
        spectral_compatibility = edge_similarity(analysis.spectral_centroid)
        bass_compatibility = edge_similarity(analysis.bass_rms)
        first_chroma = np.mean(analysis.chroma[:, first_edge], axis=1)
        last_chroma = np.mean(analysis.chroma[:, last_edge], axis=1)
        harmonic_compatibility = _cosine_similarity(first_chroma, last_chroma)
        # Compare a full bar on each side across 32 perceptual frequency bands.
        # This catches instrumentation/layer changes that total RMS and chroma
        # miss—for example equal low-end energy from a kick after the bass exits.
        first_bar = (analysis.frame_times >= start) & (analysis.frame_times < candidate_boundaries[1])
        last_bar = (analysis.frame_times >= candidate_boundaries[-2]) & (analysis.frame_times < end)
        first_bar_chroma = np.mean(analysis.chroma[:, first_bar], axis=1)
        last_bar_chroma = np.mean(analysis.chroma[:, last_bar], axis=1)
        chord_return_compatibility = _chord_transition_score(last_bar_chroma, first_bar_chroma, analysis.key_root)
        first_timbre = np.mean(analysis.spectral_profile[:, first_bar], axis=1)
        last_timbre = np.mean(analysis.spectral_profile[:, last_bar], axis=1)
        timbre_distance = float(np.mean(np.abs(first_timbre - last_timbre)))
        timbre_compatibility = float(np.exp(-timbre_distance / 0.04))
        seam_compatibility = (
            0.25 * energy_compatibility
            + 0.15 * spectral_compatibility
            + 0.20 * harmonic_compatibility
            + 0.20 * bass_compatibility
            + 0.20 * timbre_compatibility
        )

        # A loop can have similar endpoints yet still contain a buildup or bass
        # withdrawal in its final bars. Measure the direction of the last four
        # bars so those arrangement changes are not mistaken for stable loops.
        tail_size = min(4, len(bar_rms))
        tail_rms = bar_rms[-tail_size:]
        tail_bass = bar_bass[-tail_size:]

        def trend_penalty(values: np.ndarray) -> float:
            if len(values) < 2:
                return 0.0
            x = np.arange(len(values), dtype=float)
            slope = float(np.polyfit(x, values, 1)[0])
            total_change = abs(slope) * (len(values) - 1)
            relative_change = total_change / max(float(np.mean(values)), 0.08)
            return float(np.clip((relative_change - 0.10) / 0.45, 0, 1))

        energy_trend_penalty = max(trend_penalty(tail_rms), trend_penalty(tail_bass))

        # Compare the musical state across the whole phrase rather than only its
        # endpoints. A repeatable groove has similar first/last four-bar blocks;
        # a buildup has a directed trajectory in energy, brightness, or activity.
        block_bars = min(4, max(1, bars // 2))
        early_end = candidate_boundaries[block_bars]
        late_start = candidate_boundaries[-block_bars - 1]
        early_block = (analysis.frame_times >= start) & (analysis.frame_times < early_end)
        late_block = (analysis.frame_times >= late_start) & (analysis.frame_times < end)
        early_profile = np.mean(analysis.spectral_profile[:, early_block], axis=1)
        late_profile = np.mean(analysis.spectral_profile[:, late_block], axis=1)
        block_timbre = float(np.exp(-np.mean(np.abs(early_profile - late_profile)) / 0.055))
        early_state = np.array(
            [
                np.mean(analysis.rms[early_block]),
                np.mean(analysis.bass_rms[early_block]),
                np.mean(analysis.percussion_rms[early_block]),
                np.mean(analysis.onset[early_block]),
                np.mean(analysis.spectral_centroid[early_block]),
            ]
        )
        late_state = np.array(
            [
                np.mean(analysis.rms[late_block]),
                np.mean(analysis.bass_rms[late_block]),
                np.mean(analysis.percussion_rms[late_block]),
                np.mean(analysis.onset[late_block]),
                np.mean(analysis.spectral_centroid[late_block]),
            ]
        )
        state_distance = float(
            np.mean(np.abs(early_state - late_state) / np.maximum(np.maximum(early_state, late_state), 0.10))
        )
        structure_consistency = float(np.clip(0.55 * block_timbre + 0.45 * np.exp(-2.5 * state_distance), 0, 1))

        bar_onset = _means_by_bar(analysis.onset, analysis.frame_times, candidate_boundaries)
        bar_brightness = _means_by_bar(analysis.spectral_centroid, analysis.frame_times, candidate_boundaries)

        def directed_change(values: np.ndarray, direction: float = 1.0) -> float:
            if len(values) < 3:
                return 0.0
            x = np.arange(len(values), dtype=float)
            slope = float(np.polyfit(x, values, 1)[0]) * direction
            change = max(0.0, slope * (len(values) - 1))
            correlation = float(np.corrcoef(x, values)[0, 1]) * direction
            if not np.isfinite(correlation):
                correlation = 0.0
            relative = change / max(float(np.mean(values)), 0.08)
            return float(np.clip(relative * max(0.0, correlation), 0, 1))

        buildup_penalty = float(
            np.clip(
                0.35 * directed_change(bar_rms)
                + 0.25 * directed_change(bar_onset)
                + 0.20 * directed_change(bar_brightness)
                + 0.20 * directed_change(bar_bass, direction=-1.0),
                0,
                1,
            )
        )

        # Look just beyond the candidate end. A sudden arrangement change there
        # often means the selected phrase contains a buildup aimed at a drop or
        # breakdown; resetting it to bar one sounds conspicuous even if endpoint
        # levels happen to match.
        post_end = (analysis.frame_times >= end) & (analysis.frame_times < min(duration, end + 4 * beat_duration))
        if np.any(post_end):
            post_timbre = np.mean(analysis.spectral_profile[:, post_end], axis=1)
            continuation_timbre_change = 1.0 - float(np.exp(-np.mean(np.abs(last_timbre - post_timbre)) / 0.05))
            last_bass = float(np.mean(analysis.bass_rms[last_bar]))
            post_bass = float(np.mean(analysis.bass_rms[post_end]))
            continuation_bass_change = 1.0 - float(
                np.exp(-abs(last_bass - post_bass) / max(last_bass, post_bass, 0.08))
            )
            boundary_window = (analysis.frame_times >= end - 0.5 * beat_duration) & (
                analysis.frame_times < end + 0.5 * beat_duration
            )
            boundary_flux = float(np.percentile(analysis.spectral_flux[boundary_window], 80))
            typical_flux = max(float(np.percentile(flux, 80)), 0.05)
            boundary_flux_penalty = float(np.clip((boundary_flux / typical_flux - 1.25) / 1.75, 0, 1))
            boundary_transition_penalty = float(
                np.clip(
                    0.45 * continuation_timbre_change + 0.35 * continuation_bass_change + 0.20 * boundary_flux_penalty,
                    0,
                    1,
                )
            )
            post_chroma = np.mean(analysis.chroma[:, post_end], axis=1)
            natural_resolution = _chord_transition_score(last_bar_chroma, post_chroma, analysis.key_root)
            # If the original next bar resolves the ending chord much more
            # convincingly than the artificial return to bar one, the phrase is
            # likely harmonically directional rather than safely cyclic.
            harmonic_resolution_risk = float(
                np.clip(
                    (natural_resolution - chord_return_compatibility - 0.04) / 0.35,
                    0.0,
                    1.0,
                )
            )
            post_to_start_timbre = float(np.exp(-np.mean(np.abs(post_timbre - first_timbre)) / 0.045))
            post_to_start_harmony = _cosine_similarity(post_chroma, first_chroma)
            first_bass = float(np.mean(analysis.bass_rms[first_bar]))
            post_to_start_bass = float(np.exp(-abs(post_bass - first_bass) / max(post_bass, first_bass, 0.08)))
            tail_release_compatibility = float(
                np.clip(
                    0.45 * post_to_start_timbre + 0.30 * post_to_start_harmony + 0.25 * post_to_start_bass,
                    0,
                    1,
                )
            )
        else:
            boundary_transition_penalty = 0.5
            tail_release_compatibility = 0.5
            harmonic_resolution_risk = 0.25

        # Inspect the bar before entry and the bar after exit. The entry should
        # naturally lead into the unit, while the exit should not reveal that the
        # unit was merely the runway to a radically different section.
        pre_start = max(0.0, start - 4 * beat_duration)
        before = (analysis.frame_times >= pre_start) & (analysis.frame_times < start)
        if np.any(before) and np.any(post_end):
            before_state = np.mean(analysis.spectral_profile[:, before], axis=1)
            after_state = np.mean(analysis.spectral_profile[:, post_end], axis=1)
            entry_match = float(np.exp(-np.mean(np.abs(before_state - first_timbre)) / 0.07))
            exit_match = float(np.exp(-np.mean(np.abs(last_timbre - after_state)) / 0.07))
            context_compatibility = 0.55 * entry_match + 0.45 * exit_match
        else:
            context_compatibility = 0.5

        # Compare four musical bars before and after the candidate, rather than
        # judging only the waveform at the cut. This models arrangement flow:
        # stable groove, buildup, breakdown, bass withdrawal, or fade.
        before_boundaries = boundaries[max(0, index - 4) : index + 1]
        after_boundaries = boundaries[index + bars : min(len(boundaries), index + bars + 5)]
        before_energy = _means_by_bar(analysis.rms, analysis.frame_times, before_boundaries)
        after_energy = _means_by_bar(analysis.rms, analysis.frame_times, after_boundaries)
        after_bass = _means_by_bar(analysis.bass_rms, analysis.frame_times, after_boundaries)

        candidate_energy_slope = _normalized_slope(bar_rms)
        candidate_bass_slope = _normalized_slope(bar_bass)
        before_energy_slope = _normalized_slope(before_energy)
        after_energy_slope = _normalized_slope(after_energy)

        entry_energy_match = 0.65
        exit_energy_match = 0.65
        if len(before_energy):
            entry_energy_match = float(
                np.exp(-abs(before_energy[-1] - bar_rms[0]) / max(before_energy[-1], bar_rms[0], 0.08))
            )
        if len(after_energy):
            exit_energy_match = float(
                np.exp(-abs(bar_rms[-1] - after_energy[0]) / max(bar_rms[-1], after_energy[0], 0.08))
            )
        direction_match = (
            float(
                np.exp(
                    -1.25
                    * (
                        abs(candidate_energy_slope - before_energy_slope)
                        + abs(candidate_energy_slope - after_energy_slope)
                    )
                )
            )
            if len(before_energy) and len(after_energy)
            else 0.60
        )
        energy_context_match = float(
            np.clip(
                0.35 * entry_energy_match + 0.35 * exit_energy_match + 0.30 * direction_match,
                0.0,
                1.0,
            )
        )

        post_jump = 0.0
        if len(after_energy):
            post_jump = max(
                0.0,
                (after_energy[0] - bar_rms[-1]) / max(after_energy[0], bar_rms[-1], 0.08),
            )
        buildup_risk = float(
            np.clip(
                0.45 * buildup_penalty + 0.35 * max(0.0, candidate_energy_slope) + 0.20 * post_jump,
                0.0,
                1.0,
            )
        )

        continuation_bass_drop = 0.0
        if len(after_bass):
            continuation_bass_drop = max(
                0.0,
                (bar_bass[-1] - after_bass[0]) / max(bar_bass[-1], after_bass[0], 0.08),
            )
        bass_reset_risk = float(
            np.clip(
                0.50 * (1.0 - bass_compatibility)
                + 0.30 * min(1.0, abs(candidate_bass_slope))
                + 0.20 * continuation_bass_drop,
                0.0,
                1.0,
            )
        )

        if buildup_risk >= 0.45:
            energy_shape = "buildup"
        elif candidate_bass_slope <= -0.35:
            energy_shape = "losing-bass"
        elif candidate_energy_slope <= -0.30:
            energy_shape = "fading"
        elif energy_context_match < 0.45:
            energy_shape = "section-change"
        else:
            energy_shape = "stable"

        region_onset = max(float(np.percentile(onset, 75)), 0.05)
        ending_onset = float(np.percentile(analysis.onset[last_edge], 75))
        fill_penalty = float(np.clip((ending_onset / region_onset - 1.35) / 1.65, 0, 1))

        pickup_source = vocal_energy if vocal_energy is not None else analysis.harmonic_rms
        region_pickup = max(float(np.mean(pickup_source[mask])), 0.05)
        ending_pickup = float(np.mean(pickup_source[last_edge]))
        pickup_penalty = float(np.clip((ending_pickup / region_pickup - 1.20) / 1.30, 0, 1))

        edge_flux = float(np.mean(analysis.spectral_flux[last_edge]))
        region_flux = max(float(np.mean(flux)), 0.05)
        flux_penalty = float(np.clip((edge_flux / region_flux - 1.4) / 1.6, 0, 1))
        transition = float(
            np.clip(
                0.45 * (1.0 - seam_compatibility) + 0.30 * fill_penalty + 0.15 * pickup_penalty + 0.10 * flux_penalty,
                0,
                1,
            )
        )
        silence_penalty = max(0.0, 0.18 - loudness) * 3.0
        vocal = float(np.mean(vocal_energy[mask])) if vocal_energy is not None else None

        window_position = (start - search_start) / max(search_end - search_start, 1e-6)
        location_preference = 1.0 - window_position if position == "intro" else window_position
        peak_penalty = max(0.0, loudness - 0.72) if position == "intro" else 0.0

        score = (
            0.27 * rhythmic
            + 0.12 * activity
            + 0.25 * stability
            + 0.24 * instrumentalness
            + 0.10 * location_preference
            + 0.05 * loudness
            + 0.20 * arrangement_fit
            + 0.10 * local_grid_confidence
            + 0.12 * boundary_grid_confidence
            + 0.18 * regional_compatibility
        )
        score -= (
            0.30 * transition
            + 0.25 * (1.0 - timbre_compatibility)
            + 0.22 * energy_trend_penalty
            + 0.24 * boundary_transition_penalty
            + 0.30 * buildup_penalty
            + 0.24 * (1.0 - structure_consistency)
            + 0.32 * (1.0 - tail_release_compatibility)
            + 0.35 * peak_penalty
            + silence_penalty
            + 0.38 * buildup_risk
            + 0.34 * bass_reset_risk
            + 0.22 * (1.0 - energy_context_match)
            + 0.22 * (1.0 - chord_return_compatibility)
            + 0.38 * harmonic_resolution_risk
            + 0.34 * regional_boundary_risk
        )
        if vocal is not None:
            score -= 0.30 * float(np.clip(vocal, 0, 1)) + 0.72 * vocal_phrase_penalty + 0.85 * vocal_boundary_risk
        candidates.append(
            SectionCandidate(
                start,
                end,
                score,
                rhythmic,
                stability,
                transition,
                vocal,
                instrumentalness,
                seam_compatibility,
                harmonic_compatibility,
                fill_penalty,
                pickup_penalty,
                0.0,
                bass_compatibility,
                energy_trend_penalty,
                timbre_compatibility,
                boundary_transition_penalty,
                structure_consistency,
                buildup_penalty,
                context_compatibility,
                bars,
                1,
                tail_release_compatibility,
                vocal_coverage,
                vocal_boundary_risk,
                vocal_phrase_penalty,
                energy_shape,
                buildup_risk,
                bass_reset_risk,
                energy_context_match,
                chord_return_compatibility=chord_return_compatibility,
                harmonic_resolution_risk=harmonic_resolution_risk,
                section_label=section_label,
                section_confidence=section_confidence,
                arrangement_fit=arrangement_fit,
                local_grid_confidence=local_grid_confidence,
                boundary_grid_confidence=boundary_grid_confidence,
                regional_style=(candidate_behavior.style if candidate_behavior else "unknown"),
                regional_compatibility=regional_compatibility,
                regional_boundary_risk=regional_boundary_risk,
            )
        )

    if not candidates:
        raise RuntimeError(f"No complete {bars}-bar {position} candidate exists in the search window")
    return sorted(
        candidates,
        key=lambda candidate: candidate.score + 0.003 * candidate.loop_quality,
        reverse=True,
    )


def rank_sections(
    analysis: TrackAnalysis,
    bars: int,
    position: Literal["intro", "outro"],
    duration: float,
    search_seconds: float,
    vocal_energy: np.ndarray | None = None,
    maximum_end: float | None = None,
    minimum_start: float | None = None,
    count: int = 3,
) -> list[SectionCandidate]:
    """Choose a stable loop unit that supplies the requested extension length.

    A requested 16-bar extension may use one 16-bar unit, two repeats of a cleaner
    8-bar unit, or four repeats of a clean 4-bar groove. Longer units receive a
    modest preference so shorter repetition is chosen only when structurally safer.
    """
    unit_sizes = {bars, 8 if bars >= 8 else bars, 4 if bars >= 8 else bars}
    # A hard vocal entrance can leave fewer than four clean opening bars. In
    # that case a stable two-bar drum bed is preferable to repeating lyrics.
    if (maximum_end is not None or minimum_start is not None) and bars >= 8:
        unit_sizes.add(2)
    ordered_unit_sizes = sorted(unit_sizes, reverse=True)
    options: list[SectionCandidate] = []
    for unit_bars in ordered_unit_sizes:
        if bars % unit_bars:
            continue
        try:
            candidates = _rank_fixed_sections(
                analysis,
                unit_bars,
                position,
                duration,
                search_seconds,
                vocal_energy,
                maximum_end,
                minimum_start,
            )
        except RuntimeError:
            continue
        repetitions = bars // unit_bars
        length_preference = 0.035 * np.log2(unit_bars / 4.0) if unit_bars > 4 else 0.0
        repetition_penalty = 0.025 * (repetitions - 1)
        options.extend(
            replace(
                candidate,
                score=candidate.score + length_preference - repetition_penalty,
                unit_bars=unit_bars,
                repetitions=repetitions,
            )
            for candidate in candidates
        )
    if not options:
        raise RuntimeError(f"No loopable phrase can supply a {bars}-bar {position}")

    if position == "intro":
        # An extended mix should sound like a longer version of *this song's
        # opening*, not like a clean verse loop pasted in front.  Prefer material
        # rooted in the first few bars whenever it clears a modest safety floor.
        identity_boundary = float(analysis.bar_boundaries[min(INTRO_IDENTITY_BARS, len(analysis.bar_boundaries) - 1)])
        global_best = max(
            options,
            key=lambda candidate: candidate.score + 0.004 * candidate.loop_quality,
        )
        opening_options = [
            candidate
            for candidate in options
            if candidate.start < identity_boundary
            and candidate.section_label == "intro"
            and candidate.loop_quality >= MINIMUM_OPENING_IDENTITY_QUALITY
            and candidate.score >= global_best.score - OPENING_IDENTITY_SCORE_TOLERANCE
        ]
        if opening_options:
            # Once a credible true-opening phrase exists, later material is not
            # silently substituted. Alternatives remain different opening units.
            options = opening_options
    # Two bars are useful only when the protected pre-vocal opening physically
    # cannot hold four complete bars. Repeating such a short motif many times can
    # sound mechanical even when its splice metrics are excellent.
    if (maximum_end is not None or minimum_start is not None) and any(option.unit_bars >= 4 for option in options):
        options = [option for option in options if option.unit_bars >= 4]
    # An 8-bar candidate is two adjacent four-bar phrases in their original
    # order. Prefer it over A+A when it is close enough to the numerical winner,
    # has compatible halves, and does not introduce a materially worse seam.
    first = _choose_with_unique_material(options)
    if first.loop_quality < PREFERRED_LOOP_QUALITY_TARGET:
        target_options = [
            candidate
            for candidate in options
            if candidate.loop_quality >= PREFERRED_LOOP_QUALITY_TARGET
            and candidate.score >= first.score - PREFERRED_QUALITY_SCORE_TOLERANCE
            and candidate.arrangement_fit >= first.arrangement_fit - 0.15
        ]
        if target_options:
            first = max(
                target_options,
                key=lambda candidate: (
                    candidate.score + 0.004 * candidate.loop_quality,
                    candidate.unit_bars,
                ),
            )
    ranked = [first]
    remaining = sorted(
        (candidate for candidate in options if candidate is not first),
        key=lambda candidate: candidate.score + 0.004 * candidate.loop_quality,
        reverse=True,
    )
    for candidate in remaining:
        # Do not present the same musical location at several unit lengths as
        # separate choices. Alternatives should be meaningfully different.
        if any(
            min(candidate.end, chosen.end) - max(candidate.start, chosen.start)
            > 0.60 * min(candidate.end - candidate.start, chosen.end - chosen.start)
            for chosen in ranked
        ):
            continue
        ranked.append(candidate)
        if len(ranked) >= max(1, count):
            break
    return ranked


def select_section(
    analysis: TrackAnalysis,
    bars: int,
    position: Literal["intro", "outro"],
    duration: float,
    search_seconds: float,
    vocal_energy: np.ndarray | None = None,
    maximum_end: float | None = None,
    minimum_start: float | None = None,
) -> SectionCandidate:
    """Return the best of the three internally ranked candidates."""
    return rank_sections(
        analysis,
        bars,
        position,
        duration,
        search_seconds,
        vocal_energy,
        maximum_end,
        minimum_start,
        count=3,
    )[0]
