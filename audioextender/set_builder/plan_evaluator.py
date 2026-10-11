"""Deterministic quality measurements for generated Set Builder plans."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any


def _requested_terms(journey: dict[str, Any]) -> set[str]:
    return {
        str(value).strip().casefold()
        for section in journey.get("sections", [])
        for value in section.get("genres", [])
        if str(value).strip()
    }


def _track_terms(track: dict[str, Any]) -> set[str]:
    genre = str(track.get("genre") or "")
    values = [genre, *track.get("detailedGenres", [])]
    values.extend(descriptor.get("value", "") for descriptor in track.get("descriptors", []))
    return {term for value in values for raw in re.split(r"[,/|]", str(value).casefold()) if (term := raw.strip())}


@dataclass(frozen=True)
class SetPlanEvaluator:
    """Score reproducible plan characteristics without making subjective AI claims."""

    def evaluate(
        self,
        plan: list[dict[str, Any]],
        journey: dict[str, Any],
        warnings: list[dict[str, Any]],
        *,
        target_duration_minutes: int,
        candidate_pool: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tier_counts = Counter(str(track.get("matchTier") or "unknown") for track in plan)
        artists = Counter(str(track.get("artist") or "").strip().casefold() for track in plan)
        repeated_artists = sum(max(0, count - 1) for artist, count in artists.items() if artist)
        requested = _requested_terms(journey)
        matched = {term for term in requested if any(term in _track_terms(track) for track in plan)}
        missing = requested - matched
        pool_candidates = {
            str(candidate.get("id") or ""): candidate
            for section in (candidate_pool or {}).get("sections", [])
            for candidate in section.get("candidates", [])
            if candidate.get("available") and candidate.get("id")
        }
        scarcity = [
            {
                "genre": term,
                "availableCandidateCount": sum(
                    term in _track_terms(candidate) for candidate in pool_candidates.values()
                ),
            }
            for term in sorted(missing)
        ]
        section_ids = {str(section.get("id") or "") for section in journey.get("sections", [])}
        covered_sections = {str(track.get("sectionId") or "") for track in plan}
        duration_minutes = round(sum(float(track.get("durationSeconds") or 0) for track in plan) / 60, 1)
        duration_error = round(
            abs(duration_minutes - target_duration_minutes) / max(1, target_duration_minutes) * 100, 1
        )
        warning_counts = Counter(str(warning.get("code") or "unknown") for warning in warnings)
        direct = tier_counts["direct"]
        expanded = tier_counts["identity"] + tier_counts["bridge"] + tier_counts["fallback"]
        quality_score = round(
            max(
                0,
                100
                - duration_error * 0.8
                - repeated_artists * 4
                - warning_counts["large-bpm-jump"] * 6
                - warning_counts["weak-key-transition"] * 3
                - warning_counts["vocal-collision"] * 5
                - tier_counts["fallback"] * 3,
            )
        )
        disclosures = [
            f"{direct} direct match{'es' if direct != 1 else ''}, "
            f"{tier_counts['identity']} identity match{'es' if tier_counts['identity'] != 1 else ''}, "
            f"{tier_counts['bridge']} bridge track{'s' if tier_counts['bridge'] != 1 else ''}, and "
            f"{tier_counts['fallback']} flow-only fallback{'s' if tier_counts['fallback'] != 1 else ''} were used."
        ]
        if expanded:
            disclosures.append(
                f"{expanded} track{'s' if expanded != 1 else ''} expanded beyond a direct genre match "
                "to preserve journey coverage, duration, or flow."
            )
        for item in scarcity:
            if item["availableCandidateCount"] == 0:
                disclosures.append(
                    f"No available catalog candidate directly matched {item['genre']}; compatible identity or bridge "
                    "tracks preserved the section instead."
                )
        if repeated_artists:
            disclosures.append(f"The plan contains {repeated_artists} repeated-artist placement(s).")
        return {
            "version": 1,
            "qualityScore": quality_score,
            "tierCounts": dict(tier_counts),
            "warningCounts": dict(warning_counts),
            "repeatedArtistPlacements": repeated_artists,
            "requestedGenreCoverage": {
                "matched": sorted(matched),
                "missing": sorted(missing),
                "ratio": round(len(matched) / max(1, len(requested)), 3),
                "scarcity": scarcity,
            },
            "journeyCoverage": {
                "covered": len(section_ids & covered_sections),
                "total": len(section_ids),
            },
            "duration": {
                "targetMinutes": target_duration_minutes,
                "actualMinutes": duration_minutes,
                "errorPercent": duration_error,
            },
            "disclosures": disclosures,
        }
