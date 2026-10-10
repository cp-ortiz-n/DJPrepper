"""Deterministically repair structural defects in AI Set Builder proposals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlanProposalRepairer:
    """Preserve valid AI choices while filling bounded section and uniqueness gaps."""

    def repair(
        self,
        proposal: dict[str, Any],
        candidates: list[dict[str, Any]],
        section_targets: dict[str, int],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        by_id = {str(candidate.get("id") or ""): candidate for candidate in candidates}
        proposed = proposal.get("selections", [])
        proposed = proposed if isinstance(proposed, list) else []
        repaired: list[dict[str, Any]] = []
        repairs: list[dict[str, Any]] = []
        used: set[str] = set()
        for section_id, target in section_targets.items():
            eligible = [
                candidate for candidate in candidates
                if section_id in {str(value) for value in candidate.get("eligibleSectionIds", [])}
            ]
            eligible.sort(key=lambda candidate: (
                not bool(candidate.get("required") or candidate.get("locked")),
                -float(candidate.get("relevanceScore") or 0),
                str(candidate.get("id") or ""),
            ))
            section_choices: list[dict[str, Any]] = []
            forced = [candidate for candidate in eligible if candidate.get("required") or candidate.get("locked")]
            for candidate in forced:
                track_id = str(candidate.get("id") or "")
                if track_id in used or len(section_choices) >= target:
                    continue
                section_choices.append(self._selection(track_id, section_id, "Required or locked by the DJ."))
                used.add(track_id)
            for selection in proposed:
                if len(section_choices) >= target:
                    break
                if not isinstance(selection, dict):
                    continue
                track_id = str(selection.get("trackId") or "")
                proposed_candidate = by_id.get(track_id)
                if (
                    str(selection.get("sectionId") or "") != section_id
                    or proposed_candidate is None
                    or track_id in used
                    or section_id not in {
                        str(value) for value in proposed_candidate.get("eligibleSectionIds", [])
                    }
                ):
                    continue
                section_choices.append({
                    "trackId": track_id,
                    "sectionId": section_id,
                    "reason": str(selection.get("reason") or "AI-selected candidate."),
                    "evidence": "ai-suggested",
                })
                used.add(track_id)
            for candidate in eligible:
                if len(section_choices) >= target:
                    break
                track_id = str(candidate.get("id") or "")
                if not track_id or track_id in used:
                    continue
                section_choices.append(self._selection(
                    track_id, section_id, "Filled an invalid or missing AI section slot deterministically."
                ))
                used.add(track_id)
                repairs.append({"code": "filled-section-slot", "sectionId": section_id, "trackId": track_id})
            repaired.extend(section_choices)
        original_ids = [str(item.get("trackId") or "") for item in proposed if isinstance(item, dict)]
        repaired_ids = [item["trackId"] for item in repaired]
        removed_count = max(0, len(original_ids) - len(set(original_ids) & set(repaired_ids)))
        if removed_count:
            repairs.insert(0, {"code": "discarded-invalid-selections", "count": removed_count})
        return {**proposal, "selections": repaired}, repairs

    @staticmethod
    def _selection(track_id: str, section_id: str, reason: str) -> dict[str, str]:
        return {"trackId": track_id, "sectionId": section_id, "reason": reason, "evidence": "estimated"}
