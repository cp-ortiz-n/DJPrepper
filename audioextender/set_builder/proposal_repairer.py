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
        used_recordings: set[str] = set()

        def available(candidate: dict[str, Any]) -> bool:
            track_id = str(candidate.get("id") or "")
            recording_key = str(candidate.get("recordingKey") or track_id)
            return bool(track_id) and track_id not in used and recording_key not in used_recordings

        def reserve(candidate: dict[str, Any]) -> None:
            track_id = str(candidate.get("id") or "")
            used.add(track_id)
            used_recordings.add(str(candidate.get("recordingKey") or track_id))

        for section_id, target in section_targets.items():
            eligible = [
                candidate
                for candidate in candidates
                if section_id in {str(value) for value in candidate.get("eligibleSectionIds", [])}
            ]
            eligible.sort(
                key=lambda candidate: (
                    not bool(candidate.get("required") or candidate.get("locked")),
                    -float(candidate.get("relevanceScore") or 0),
                    str(candidate.get("id") or ""),
                )
            )
            section_choices: list[dict[str, Any]] = []
            forced = [candidate for candidate in eligible if candidate.get("required") or candidate.get("locked")]
            for candidate in forced:
                track_id = str(candidate.get("id") or "")
                if not available(candidate) or len(section_choices) >= target:
                    continue
                section_choices.append(self._selection(track_id, section_id, "Required or locked by the DJ."))
                reserve(candidate)
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
                    or not available(proposed_candidate)
                    or section_id not in {str(value) for value in proposed_candidate.get("eligibleSectionIds", [])}
                ):
                    continue
                section_choices.append(
                    {
                        "trackId": track_id,
                        "sectionId": section_id,
                        "reason": str(selection.get("reason") or self._candidate_reason(proposed_candidate)),
                        "evidence": "ai-suggested",
                    }
                )
                reserve(proposed_candidate)
            for candidate in eligible:
                if len(section_choices) >= target:
                    break
                track_id = str(candidate.get("id") or "")
                if not available(candidate):
                    continue
                section_choices.append(
                    self._selection(
                        track_id, section_id, "Filled an invalid or missing AI section slot deterministically."
                    )
                )
                reserve(candidate)
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

    @staticmethod
    def _candidate_reason(candidate: dict[str, Any]) -> str:
        evidence = [
            str(reason.get("text") or "").strip()
            for reason in candidate.get("reasons", [])
            if isinstance(reason, dict) and reason.get("text")
        ]
        if evidence:
            return "AI selected this controlled candidate. " + " ".join(evidence[:2])
        return (
            "AI selected this controlled candidate from its catalog genre, identity, energy, and transition metadata."
        )
