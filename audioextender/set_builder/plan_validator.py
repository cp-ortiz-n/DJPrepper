"""Deterministic safety checks for proposed Set Builder track plans."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from audioextender.set_builder.transition_optimizer import bpm_distance_ratio, weak_harmonic_transition


@dataclass(frozen=True)
class SetPlanValidator:
    """Reject unsafe plans and report softer musical risks separately."""

    duration_tolerance: float = 0.15

    def validate(
        self,
        selections: list[dict[str, Any]],
        candidates: list[dict[str, Any]],
        journey: dict[str, Any],
        *,
        required_ids: set[str] | None = None,
        excluded_ids: set[str] | None = None,
        locked_ids: set[str] | None = None,
        locked_sections: dict[str, str] | None = None,
        target_duration_minutes: int | None = None,
        target_track_count: int | None = None,
    ) -> dict[str, Any]:
        required = required_ids or set()
        excluded = excluded_ids or set()
        locked = locked_ids or set()
        locked_by_section = locked_sections or {}
        by_id = {str(candidate.get("id") or ""): candidate for candidate in candidates}
        section_ids = {str(section.get("id") or "") for section in journey.get("sections", [])}
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        chosen: list[dict[str, Any]] = []
        seen: set[str] = set()
        seen_recordings: dict[str, str] = {}
        for position, selection in enumerate(selections, start=1):
            track_id = str(selection.get("trackId") or selection.get("id") or "")
            section_id = str(selection.get("sectionId") or "")
            candidate = by_id.get(track_id)
            if candidate is None:
                errors.append({"code": "unknown-track", "trackId": track_id, "position": position})
                continue
            if track_id in seen:
                errors.append({"code": "duplicate-track", "trackId": track_id, "position": position})
            recording_key = str(candidate.get("recordingKey") or "")
            if track_id not in seen and recording_key and recording_key in seen_recordings:
                errors.append({
                    "code": "duplicate-recording",
                    "trackId": track_id,
                    "firstTrackId": seen_recordings[recording_key],
                    "recordingKey": recording_key,
                    "position": position,
                })
            if track_id in excluded:
                errors.append({"code": "excluded-track", "trackId": track_id, "position": position})
            path = str(candidate.get("path") or "")
            if not candidate.get("available") or (path and not Path(path).is_file()):
                errors.append({"code": "unavailable-file", "trackId": track_id, "position": position})
            if section_id not in section_ids:
                errors.append({"code": "unknown-section", "sectionId": section_id, "position": position})
            expected_section = locked_by_section.get(track_id)
            if expected_section and section_id != expected_section:
                errors.append({
                    "code": "locked-section-mismatch",
                    "trackId": track_id,
                    "expectedSectionId": expected_section,
                    "actualSectionId": section_id,
                    "position": position,
                })
            eligible_sections = {str(value) for value in candidate.get("eligibleSectionIds", [])}
            if eligible_sections and section_id not in eligible_sections:
                errors.append({"code": "candidate-section-mismatch", "trackId": track_id, "position": position})
            evidence = str(selection.get("evidence") or "ai-suggested")
            if evidence not in {"verified", "estimated", "ai-suggested"}:
                errors.append({"code": "invalid-evidence-label", "trackId": track_id, "position": position})
                evidence = "ai-suggested"
            if candidate.get("matchTier") in {"bridge", "fallback"}:
                warnings.append({
                    "code": "expanded-genre-match",
                    "trackId": track_id,
                    "tier": candidate["matchTier"],
                    "position": position,
                })
            seen.add(track_id)
            if recording_key:
                seen_recordings.setdefault(recording_key, track_id)
            chosen.append({
                **candidate,
                "sectionId": section_id,
                "position": position,
                "selectionReason": {
                    "evidence": evidence,
                    "text": str(selection.get("reason") or "").strip()[:500],
                },
            })
        for track_id in sorted((required | locked) - seen):
            errors.append({"code": "missing-required-track", "trackId": track_id})
        missing_sections = section_ids - {track["sectionId"] for track in chosen}
        for section_id in sorted(missing_sections):
            errors.append({"code": "empty-journey-section", "sectionId": section_id})
        if target_track_count is not None and len(chosen) != target_track_count:
            errors.append({"code": "track-count-mismatch", "expected": target_track_count, "actual": len(chosen)})
        duration_seconds = sum(float(track.get("durationSeconds") or 0) for track in chosen)
        if target_duration_minutes:
            target_seconds = target_duration_minutes * 60
            difference = abs(duration_seconds - target_seconds) / target_seconds
            if difference > self.duration_tolerance:
                errors.append({
                    "code": "duration-outside-tolerance",
                    "expectedMinutes": target_duration_minutes,
                    "actualMinutes": round(duration_seconds / 60, 1),
                })
        for index, right in enumerate(chosen[1:], start=1):
            left = chosen[index - 1]
            if bpm_distance_ratio(left, right) > 0.12:
                warnings.append({"code": "large-bpm-jump", "from": left["id"], "to": right["id"]})
            if weak_harmonic_transition(left, right):
                warnings.append({"code": "weak-key-transition", "from": left["id"], "to": right["id"]})
            if left.get("vocals") == right.get("vocals") == "vocal-forward":
                warnings.append({"code": "vocal-collision", "from": left["id"], "to": right["id"]})
        return {
            "version": 1,
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "metrics": {
                "tracks": len(chosen),
                "durationMinutes": round(duration_seconds / 60, 1),
                "sectionsCovered": len(section_ids - missing_sections),
                "sectionsTotal": len(section_ids),
            },
            "plan": chosen,
        }
