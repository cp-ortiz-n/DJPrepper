"""Deterministic safety checks for proposed Set Builder track plans."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


def _camelot(value: str) -> tuple[int, str] | None:
    match = re.fullmatch(r"(1[0-2]|[1-9])([AB])", value.strip().upper())
    return (int(match.group(1)), match.group(2)) if match else None


def _harmonic_warning(left: dict[str, Any], right: dict[str, Any]) -> bool:
    first = _camelot(str(left.get("camelot") or left.get("key") or ""))
    second = _camelot(str(right.get("camelot") or right.get("key") or ""))
    if not first or not second:
        return False
    distance = min((first[0] - second[0]) % 12, (second[0] - first[0]) % 12)
    return distance > 1 or (first[1] != second[1] and first[0] != second[0])


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
        target_duration_minutes: int | None = None,
        target_track_count: int | None = None,
    ) -> dict[str, Any]:
        required = required_ids or set()
        excluded = excluded_ids or set()
        locked = locked_ids or set()
        by_id = {str(candidate.get("id") or ""): candidate for candidate in candidates}
        section_ids = {str(section.get("id") or "") for section in journey.get("sections", [])}
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        chosen: list[dict[str, Any]] = []
        seen: set[str] = set()
        for position, selection in enumerate(selections, start=1):
            track_id = str(selection.get("trackId") or selection.get("id") or "")
            section_id = str(selection.get("sectionId") or "")
            candidate = by_id.get(track_id)
            if candidate is None:
                errors.append({"code": "unknown-track", "trackId": track_id, "position": position})
                continue
            if track_id in seen:
                errors.append({"code": "duplicate-track", "trackId": track_id, "position": position})
            if track_id in excluded:
                errors.append({"code": "excluded-track", "trackId": track_id, "position": position})
            if not candidate.get("available"):
                errors.append({"code": "unavailable-file", "trackId": track_id, "position": position})
            if section_id not in section_ids:
                errors.append({"code": "unknown-section", "sectionId": section_id, "position": position})
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
            bpm_left, bpm_right = float(left.get("bpm") or 0), float(right.get("bpm") or 0)
            if bpm_left and bpm_right and abs(bpm_left - bpm_right) / min(bpm_left, bpm_right) > 0.12:
                warnings.append({"code": "large-bpm-jump", "from": left["id"], "to": right["id"]})
            if _harmonic_warning(left, right):
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
